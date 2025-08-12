#!/usr/bin/python3
import os
import sys
import re
import time
import json
import dill
import socket
import select
import getpass
import marshal
import paramiko
import textwrap
import subprocess

from . import utils
from . import jenkins
log = utils.log

CONSOLE_TIMEOUT = 2400


class Container(object):
	def __init__(self, node, contId):
		self.node = node
		self.contId = contId

	def runCmd(self, *cmd, cwd=None, env={}, **kwargs):
		contCmd = ''
		for name, value in env.items():
			contCmd += f'export {name}="{value}"; '
		if cwd:
			contCmd += f'cd {cwd}; '
		contCmd += ' '.join(cmd)
		return self.node.runCmd('docker', 'exec', self.contId, 'sh', '-c', f"'{contCmd}'", **kwargs)

	def stop(self):
		log(f'Stoping: {self.contId}')
		ret, out = self.node.runCmd('docker', 'container', 'stop', self.contId)
		if ret != 0:
			log('Failed to stop container')
			return False
		return True

	def remove(self):
		self.stop()
		log(f'Removing: {self.contId}')
		ret, out = self.node.runCmd('docker', 'container', 'rm', self.contId)
		if ret != 0:
			log('Failed to remove container')
			return False
		return True


class Docker(object):
	def __init__(self, node):
		self.node = node
		self.runCmd = node.runCmd

	def pull(self, url):
		for i in range(3):
			ret, out = self.runCmd('docker', 'pull', url)
			errExpr = 'Failed to fetch|Transaction failed|Connection failed'
			if ret == 0 or not re.search(errExpr, out):
				break
			log('docker-pull: Failed due to network issue')
			log('Retrying after 2min...')
			time.sleep(120)
		return bool(ret == 0)

	def rm(self, tagExpr='', excludeExpr='', olderThanDays=0, verbose=False):
		ret, out = self.runCmd('docker', 'image', 'ls',
			#'--filter', 'dangling=true',
			'--format', '{{.ID}},{{.CreatedAt}},{{.Tag}}',
			verbose=verbose,
		)
		deleteFrom = time.time() - (olderThanDays * (24*3600))
		ret = True
		for line in out.splitlines():
			imageId, createdAt, tag = line.split(',')
			createdAt = time.mktime(time.strptime(
				createdAt.rsplit(maxsplit=2)[0], '%Y-%m-%d %H:%M:%S'
			))
			if not re.search(excludeExpr, tag) and re.search(tagExpr, tag) and (createdAt < deleteFrom):
				ret, out = self.runCmd('docker', 'image', 'rm', '--force=true', imageId, verbose=verbose)
				if ret == 0:
					log(f'Removed: {tag}')
					continue
				log(f'Remove Failed: {tag}')
				ret = False
		return ret

	############## enhance these docker apis ####################
	def run(self, imgName='', contName='', volume=''):
		self.runCmd('docker', 'run', '-d', '-it', f'--name={contName}'
			'--network=host', '--device=/dev/kfd', '--device=/dev/dri'
			'--group-add', 'video', '--cap-add=SYS_PTRACE'
			'--security-opt', 'seccomp=unconfined'
			'--ipc=host', '-v', volume, imgName,
		)

	def exec(self, contName='', cmd='', workDir=''):
		if workDir:
			self.runCmd(
				f"docker exec -w {workDir} -i {contName} /bin/bash -c '{cmd}'"
			)
		else:
			self.runCmd(f"docker exec -i {contName} /bin/bash -c '{cmd}'")


class Node(object):
	def __init__(self):
		self.homeDir = None
		self.hostname = None
		self.osDetails = {}
		self.env = {}
		self.docker = Docker(self)
		self.ncpu = None
		self.ngpu = None
		self.errors = []
		self.passwd = None

	def getIp(self, host=None):
		sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
		sock.connect(('8.8.8.8', 80))
		ip, port = s.getsockname()
		sock.close()
		return ip

	def isHydMachine(self):
		return self.getIp().startswith('10.130')

	def runCmd(self, *cmd, cwd=None, env={}, stdin=None, timeout=CONSOLE_TIMEOUT, attempts=1, teeFd=None, nowait=False, verbose=True):
		# todo: implement timeout, attempts and teeFd logics
		if verbose != None:
			cwdStr = f'cd {cwd}; ' if cwd else ''
			sys.stdout.write(f'RunCmd: {cwdStr}{" ".join(cmd)}\n')
			sys.stdout.flush()
		# launch process
		cmdEnv = os.environ.copy()
		cmdEnv.update(env)
		process = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
			stderr=subprocess.STDOUT, cwd=cwd, env=cmdEnv,
		)
		# handling stdin
		if isinstance(stdin, str):
			process.stdin.write(stdin if isinstance(stdin, bytes) else stdin.encode())
		elif isinstance(stdin, bytes):
			process.stdin.write(stdin if isinstance(stdin, bytes) else stdin.encode())
		elif isinstance(stdin, type(process.stdout)):
			chunk = None
			while chunk != b'':
				chunk = stdin.read(1024)
				process.stdin.write(chunk)
		process.stdin.close()
		if nowait:  # background process
			return process
		# following process stdout / stderr
		verbose and sys.stdout.write('out:\n') and sys.stdout.flush()
		out = ''
		chunk = None
		while chunk != b'':
			chunk = process.stdout.read(1)
			verbose and sys.stdout.buffer.write(chunk) and sys.stdout.flush()
			out += chunk.decode(errors='replace')
		# handling return value
		ret = process.wait()
		if ret != 0 and verbose != None:
			sys.stderr.write(f'cmd failed: {" ".join(cmd)}\n')
			verbose or sys.stderr.write(f'err: {out}\n') and sys.stderr.flush()
			self.errors.append((' '.join(cmd), ret, '\n'.join(out.splitlines()[-15:])))
		verbose and sys.stdout.write(f'ret: {ret}\n') and sys.stdout.flush()
		return ret, out

	def runPy(self, funcPtr, args, *helperFuncs, cwd=None, pudo=False, env={}, timeout=CONSOLE_TIMEOUT, verbose=True, teeFd=None, nowait=False):
		if cwd:
			_cwd = os.getcwd()
			os.chdir(cwd)
		if env:
			_env = os.environ.copy()
			os.environ.update(self.env)
			os.environ.update(env)
		if env:
			os.environ = _env
		cwd and os.chdir(_cwd)
		_locals = locals()
		for fPtr in helperFuncs:
			_locals[fPtr.__name__] = fPtr
		ret = funcPtr(*args)
		verbose and log(f'ret: {ret}')
		return ret

	def writeFile(self, filepath, content, cwd=None, pudo=False, verbose=False):
		return self.runCmd(('', 'pudo')[pudo], 'tee', filepath, stdin=content, cwd=cwd, verbose=verbose)

	def readFile(self, filepath, cwd=None, pudo=False, verbose=False):
		ret, out = self.runCmd(('', 'pudo')[pudo], 'cat', filepath, cwd=cwd, verbose=verbose)
		if ret != 0:
			return None
		return out

	def _getPasswd(self):
		if not self.passwd:
			self.passwd = getpass.getpass('sudo passwd please:')
		return self.passwd

	def installPudo(self):
		cmd = ('pudo', 'ls', '/root')
		ret, out = self.runCmd(*cmd, verbose=None)
		if ret == 0:
			return True
		if ret not in (1, 127): # something unexpected happen
			ret, out = self.runCmd(*cmd)
			return bool(ret)
		self._getPasswd()
		sudoCmd = ('sudo', '-S', '-E')
		if ret == 127:
			check, update, install, info, remove = self.getPkgMngr()
			for pkg in ('gcc', 'python3', 'python3-pip'):
				ret, out = self.runCmd(*sudoCmd, *check[1:], pkg, stdin=self.passwd, verbose=None)
				if ret == 0:
					continue
				ret, out = self.runCmd(*sudoCmd, *install[1:], pkg, stdin=self.passwd, timeout=300)
				if ret != 0:
					log(f'Failed to install: {pkg}\n{out}')
					return False
			pipCmd = self.getPipCmd()
			ret, out = self.runCmd(*sudoCmd, *pipCmd[1:], 'install', 'pudo', stdin=self.passwd, verbose=None)
			if ret != 0:
				log(f'Failed to install pudo command\n{out}')
				return False
			ret = 1	# to accept the disclamer
		if ret == 1 or '--accept-disclamer' in out:
			self.runCmd(*sudoCmd, 'pudo', '--accept-disclamer', stdin=self.passwd, verbose=None)
		return True

	def reboot(self):
		log('Cannot reboot the local machine')
		return True

	def getHomeDir(self):
		return os.environ['HOME']

	def getHostname(self):
		if not self.hostname:
			self.hostname = socket.gethostname()
		return self.hostname

	def getOsDetails(self):
		if not self.osDetails:
			content = self.readFile('/etc/os-release', pudo=True, verbose=None)
			self.osDetails = dict(re.findall(r'(\w+)="?([^"\n]+)', content))
		return self.osDetails

	def getSrcListDetails(self):
		osDetails = self.getOsDetails()
		srcListDir, srcListExt = {
			'ubuntu': ('/etc/apt/sources.list.d', 'list'),
			'rhel': ('/etc/yum.repos.d', 'repo'),
			'centos': ('/etc/yum.repos.d', 'repo'),
			'sles': ('/etc/zypp/repos.d', 'repo'),
			'mariner': ('/etc/zypp/repos.d', 'repo'),
		}[osDetails['ID']]
		return srcListDir, srcListExt

	def getPkgMngr(self):
		osDetails = self.getOsDetails()
		base = ('pudo', )
		aptBase = (*base, 'apt')
		zprBase = (*base, 'zypper')
		dnfBase = (*base, 'dnf')
		yumBase = (*base, 'yum')
		check, update, install, info, remove = {
			# osid: (check, update, install, info, remove),
			'ubuntu': (
				('pudo', 'dpkg-query', '--show'),
				(*aptBase, 'update'),
				(*aptBase, '-o', 'Dpkg::Options::="--force-confnew"', 'install', '--yes'),
				(*aptBase, 'show'),
				(*aptBase, 'purge', '--yes'),
			),
			'rhel': (
				(*dnfBase, 'list', '--installed'),
				(*dnfBase, 'makecache'),
				(*dnfBase, 'install', '-y'),
				(*dnfBase, 'info'),
				(*dnfBase, 'remove', '-y'),
			),
			'mariner': (
				(*dnfBase, 'list', '--installed'),
				(*dnfBase, 'makecache'),
				(*dnfBase, 'install', '-y'),
				(*dnfBase, 'info'),
				(*dnfBase, 'remove', '-y'),
			),
			'centos': (
				(*yumBase, '-qa'),
				(*yumBase, 'update'),
				(*yumBase, 'install', '-y', '--nogpgcheck'),
				(*yumBase, 'info'),
				(*yumBase, 'remove', '-y'),
			),
			'sles': (
				(*zprBase, 'search', '-i'),
				(*zprBase, 'update'),
				(*zprBase, '--no-gpg-checks', 'install', '--replacefiles', '-y'),
				(*zprBase, 'info'),
				(*zprBase, 'remove', '-y'),
			),
		}[osDetails['ID']]
		return (check, update, install, info, remove)

	def installPkgs(self, *pkgs, updateCache=False, verbose=None):
		check, update, install, info, remove = self.getPkgMngr()
		if updateCache:
			ret, out = self.runCmd(*update, verbose=verbose, attempts=3)
			if ret != 0:
				return False
		for pkg in pkgs:
			ret, out = self.runCmd(*check, pkg, verbose=None)
			if ret == 0:
				verbose and log(f'Already Installed: {out.strip()}')
				continue
			ret, out = self.runCmd(*install, pkg, verbose=verbose, attempts=3)
			if ret != 0:
				return False
		return True

	def removePkgs(self, *pkgs, verbose=None):
		check, update, install, info, remove = self.getPkgMngr()
		for pkg in pkgs:
			ret, out = self.runCmd(*check, pkg, verbose=None)
			if ret == 0:
				continue
			ret, out = self.runCmd(*remove, pkg)
			if ret != 0:
				return False
		return True

	def getPipCmd(self):
		return ('pudo', 'pip3')

	def installPipPkgs(self, *pkgs, src=None, upgrade=False, verbose=None):
		pipCmd = self.getPipCmd()
		for pkg in pkgs:
			if not upgrade:
				ret, out = self.runCmd(*pipCmd, 'show', pkg, verbose=verbose)
				if ret == 0:
					continue
			ret, out = self.runCmd(*pipCmd, 'install', ('', '--upgrade',)[upgrade],
				src or pkg, verbose=verbose,
			)
			if ret != 0:
				return False
		return True

	def syncGitRepo(self, url, branch, cwd='.', pvKey=None, verbose=False):
		if 'github-emu' in url:
			pvKey = f'{self.getHomeDir()}/.ssh/id_ed25519_emu'
			ret, out = self.runCmd('ls', pvKey, verbose=None)
			if ret != 0:
				self.writeFile(pvKey, utils.getGithubEmuPvtKey(), verbose=False)
				self.runCmd('chmod', '600', pvKey, verbose=None)
			url = re.sub('github-emu', 'git@github.com', url)
		elif 'gerritgit' in url:
			def _setupGerrit(pvKey, content):
				fd = open(pvKey, 'wb')
				fd.write(content)
				fd.close()
				os.chmod(pvKey, 0o600)
				return True
			pvKey = f'{self.getHomeDir()}/.ssh/gerrit_id_rsa'
			ret, out = self.runCmd('ls', pvKey, verbose=None)
			if ret != 0:
				content = utils.getGerritPvtKey()
				self.runPy(_setupGerrit, (pvKey, content), verbose=verbose)
		return self.runPy(utils.syncGitRepo, (url, branch, cwd, pvKey, verbose), utils.runCmd, utils.log, verbose=verbose)

	def getCpuCount(self):
		if not self.ncpu:
			ret, out = self.runCmd('nproc', verbose=None)
			self.ncpu = int(out)
		return self.ncpu

	def rocmsmi(self, verbose=True):
		ret, out = self.runCmd('rocm-smi', verbose=verbose)
		if ret == 127: # retry when rocminfo not exists
			ret, out = self.runCmd('pudo', '/opt/rocm/bin/rocm-smi', verbose=verbose)
		if ret != 0:
			return False
		self.ngpu = len(re.findall(r'\n\d', out))
		return True

	def getGpuCount(self):
		if not self.ngpu:
			self.rocmsmi(verbose=True)
		return self.ngpu

	def checkDkms(self, version=None):
		check, update, install, info, remove = self.getPkgMngr()
		ret, out = self.runCmd(*check, 'amdgpu-core', verbose=None)
		return bool(re.search(rf'-{version}\.', out)) if version else bool(ret == 0)

	def uninstallDkms(self):
		if not self.checkDkms():
			return True
		check, update, install, info, remove = self.getPkgMngr()
		ret, out = self.runCmd(*remove, r'amdgpu\*')
		return bool(ret == 0)

	def verifyDkms(self):
		ret, out = self.runCmd('pudo', '/sbin/modprobe', 'amdgpu')
		return bool(ret == 0)

	def updateAmdGpuBuildSources(self, version):
		osDetails = self.getOsDetails()
		url = 'https://artifactory-cdn.amd.com/artifactory/list'
		if osDetails['ID'] == 'ubuntu':
			content = f'deb [trusted=yes] {url}/amdgpu-deb-remote {version} {osDetails["UBUNTU_CODENAME"]}\n'
		else:
			content = '[amdgpu]\n'
			content += f'name=AMDGPU {version} repository\n'
			content += f'baseurl={url}/amdgpu-rpm/{osDetails["ID"]}/{osDetails["VERSION_ID"]}/builds/{version}/x86_64\n'
			content += 'enabled=1\n'
			content += 'gpgcheck=0\n'
		srcListDir, srcListExt = self.getSrcListDetails()
		srcListFile = f'{srcListDir}/amdgpu-build.{srcListExt}'
		self.writeFile(srcListFile, content, pudo=True)

	def installDkms(self, version):
		# check dkms version
		if self.checkDkms(version):
			log(f'Already at given dkms version: {version}')
			return True
		# uninstall dkms
		if not self.uninstallDkms():
			log(f'DKMS Uninstall failed')
			return False
		# install dkms
		self.updateAmdGpuBuildSources(version)
		if not self.installPkgs('amdgpu-core', 'amdgpu-dkms', updateCache=True, verbose=True):
			log('DKMS Installation Failed')
			return False
		log('DKMS Installation Done')
		if not self.reboot():
			return False
		return self.verifyDkms()

	def checkRocmDev(self, version=None):
		check, update, install, info, remove = self.getPkgMngr()
		ret, out = self.runCmd(*check, r'rocm-dev', verbose=False)
		return bool(re.search(rf'[-\.]{version}~', out)) if version else bool(ret == 0)

	def getRocmPath(self):
		check, update, install, info, remove = self.getPkgMngr()
		ret, out = self.runCmd(*check, r'rocm-core', verbose=None)
		if ret != 0:
			return '/opt/rocm'  # fallback to  skip test breaks
		rocmVersion = re.search(r'rocm-core\s+(\d+\.\d+\.\d+)', out).group(1)
		return f'/opt/rocm-{rocmVersion}'

	def uninstallRocmDev(self):
		if not self.checkRocmDev():
			return True
		check, update, install, info, remove = self.getPkgMngr()
		ret, out = self.runCmd(*remove, r'rocm\*')
		return bool(ret == 0)

	def verifyRocm(self):
		if not self.verifyDkms():
			return False
		ret, out = self.runCmd('ls', '/opt/rocm', verbose=False)
		if ret != 0:
			log('Error: No link found @ /opt/rocm')
			return False
		if not self.rocmsmi():
			log('Error: Failed to get rocm-smi')
			return False
		ret, out = self.runCmd('rocminfo', verbose=False)
		if ret == 127: # retry when rocminfo not exists
			ret, out = self.runCmd('pudo', '/opt/rocm/bin/rocminfo', verbose=False)
		if ret != 0:
			log('Error: Failed to get rocminfo')
			return False
		ret, out = self.runCmd('clinfo', verbose=False)
		if ret == 127: # retry when clinfo not exists
			ret, out = self.runCmd('pudo', '/opt/rocm/bin/clinfo', verbose=False)
		if ret == 127: # retry when bin/clinfo not exists
			ret, out = self.runCmd('pudo', '/opt/rocm/opencl/bin/clinfo', verbose=False)
		if ret != 0:
			log('Failed to get clinfo')
			return False
		log('Rocm Driver is healthy')
		return True

	def updateRocmBuildSources(self, buildUrl):
		repoMap = {
			'psdb': {
				'ubuntu': {
					'20.04': 'rocm-psdb-20.04-deb',
					'22.04': 'rocm-psdb-22.04-deb',
					'24.04': 'rocm-psdb-24.04-deb',
				},
			},
			'osdb': {
				'ubuntu': {
					'20.04': 'rocm-osdb-20.04-deb',
					'22.04': 'rocm-osdb-22.04-deb',
					'24.04': 'rocm-osdb-24.04-deb',
				},
				'rhel': {
					'8.x': 'rocm-osdb-rhel-8.x',
					'9.x': 'rocm-osdb-rhel-9.x',
				},
				'centos': {
					'7': 'rocm-osdb-20.04-deb',
				},
				'sles': {
					'': 'rocm-osdb-sles',
				},
				'mariner': {
					'2.x': 'rocm-osdb-mariner-2.x',
				},
			},
		}
		job, num = utils.splitBuildLink(buildUrl)
		buildType = ('osdb', 'psdb')['psdb' in buildUrl]
		osDetails = self.getOsDetails()
		repoDir = repoMap[buildType][osDetails['ID']][osDetails['VERSION_ID']]
		url = f'https://compute-artifactory.amd.com/artifactory/list/{repoDir}'
		if osDetails['ID'] == 'ubuntu':
			# signing key
			signfile = '/etc/apt/trusted.gpg.d/rocm-internal.gpg'
			ret, out = self.runCmd('ls', signfile, verbose=None)
			if ret != 0:
				self.writeFile(signfile, utils.getRocmInternalGPG(), pudo=True, verbose=False)
				self.runCmd('pudo', 'chmod', '644', signfile, verbose=None)
			content = f'deb [arch=amd64 Signed-By={signfile}] {url} {job} {num}\n'
			# artifactory pinning
			pinFile = '/etc/apt/preferences.d/rocm-pin-600'
			ret, out = self.runCmd('ls', pinFile, verbose=None)
			if ret != 0:
				pinContent = 'Package: *\nPin: release o=compute-artifactory.amd.com\nPin-Priority: 600'
				self.writeFile(pinFile, pinContent, pudo=True, verbose=False)
		else:
			content = '[rocm]\n'
			content += f'name=ROCm {job}/{num} repository\n'
			content += f'baseurl={url}/{job}-{num}\n'
			content += 'enabled=1\n'
			content += 'gpgcheck=0\n'
			content += 'priority=50\n'
		srcListDir, srcListExt = self.getSrcListDetails()
		srcListFile = f'{srcListDir}/rocm-build.{srcListExt}'
		self.writeFile(srcListFile, content, pudo=True)

	def installRocmDev(self, buildUrl):
		job, num = utils.splitBuildLink(buildUrl)
		# check dkms version
		if self.checkRocmDev(num):
			log(f'Already at given rocm-dev version: {num}')
			return self.verifyRocm()
		# uninstall rocm-dev
		if not self.uninstallRocmDev():
			log(f'RocmDev Uninstall failed')
			return False
		# install rocm-dev
		self.updateRocmBuildSources(buildUrl)
		if not self.installPkgs('rocm-core', 'rocm-dev', updateCache=True, verbose=True):
			log('Rocm Driver Installation Failed')
			return False
		log('Rocm Driver Installation Done')
		return self.verifyRocm()

	def removeDockers(self, tagExpr='', removeImg=True):
		ret, psOut = self.runCmd('docker', 'ps', '-a', verbose=False)
		ret, imagesOut = self.runCmd('docker', 'images', verbose=False)
		imageDict = {}
		# search in images
		for line in imagesOut.splitlines()[1:]:
			if not re.search(tagExpr, line):
				continue
			repository, tag, imageId = line.split()[:3]
			image = imageId
			if '<none>' not in (repository, tag):
				image = f'{repository}:{tag}'
			for containerId in re.findall(rf'(\w+).*?{imageId}', psOut):
				imageDict.setdefault(image, set()).add(containerId)
		# search in containers
		for line in psOut.splitlines()[1:]:
			if not re.search(tagExpr, line):
				continue
			containerId, image = line.split()[:2]
			if not re.search(r'[\da-f]+', image):
				repository, tag = re.search(f'(.*?) +(.*?) +{image}', imagesOut).groups()
				if '<none>' not in (repository, tag):
					image = f'{repository}:{tag}'
			imageDict.setdefault(image, set()).add(containerId)
		log(f'Identified Dockers: {imageDict}')
		# remove images
		for image, containerList in imageDict.items():
			log(f'Removing: {image}')
			# remove the containers related to given image
			for containerId in containerList:
				if not containerId:
					continue
				log(f'Removing: {containerId}')
				ret, out = self.runCmd('docker', 'container', 'stop', containerId)
				if ret != 0:
					log('Failed to stop container')
					return False
				ret, out = self.runCmd('docker', 'container', 'rm', containerId)
				if ret != 0:
					log('Failed to remove container')
					return False
			# remove the docker image
			if removeImg:
				ret, out = self.runCmd('docker', 'image', 'rm', image)
				if ret != 0:
					log('Failed to remove image')
					return False
		return True

	def configDocker(self, dockerfile, base=None, env={}, runList=(), sub=None, cwd=None):
		def _configDocker(dockerfile, base, env, runList, sub):
			fd = open(dockerfile, 'r+')
			content = fd.read()
			# update base docker
			if base:
				content = re.sub('FROM .*', f'FROM {base}', content)
			# update env vars
			for key, value in env.items():
				if key in content:
					content = re.sub(f'ENV {key}=.*', f'ENV {key}="{value}"', content)
				else:
					content = re.sub(f'\nRUN', f'\nENV {key}="{value}"\nRUN', content, 1)
			# update run cmds
			for cmd in runList:
				if cmd not in content:
					content = re.sub(f'\nRUN', f'\nRUN {cmd}\nRUN', content, 1)
			# substitutes
			if sub:
				expr, rExpr = sub
				if rExpr not in content:
					content = re.sub(expr, rExpr, content)
			fd.seek(0)
			fd.write(content)
			fd.truncate()
			fd.close()
		env.update(self.env)
		return self.runPy(_configDocker, (dockerfile, base, env, runList, sub), cwd=cwd, verbose=False)

	def findDcrImg(self, tagExpr=''):
		ret, imagesOut = self.runCmd('docker', 'images', verbose=False)
		imgList = []
		for line in imagesOut.splitlines()[1:]:
			if not re.search(tagExpr, line):
				continue
			repository, tag, imageId = line.split()[:3]
			image = imageId
			if '<none>' not in (repository, tag):
				image = f'{repository}:{tag}'
			imgList.append(image)
		return imgList

	def runDocker(self, image, *options, cwd=None):
		ret, out = self.runCmd('docker', 'run', '--tty', '--detach', *options, image, cwd=cwd)
		if ret != 0:
			return None
		contId = out.strip()[:12]
		return Container(self, contId)

	def rmDcrImg(self, tagExpr=''):
		imgList = self.findDcrImg(tagExpr)
		for image in imgList:
			log(f'Removing: {image}')
			ret, out = self.runCmd('docker', 'image', 'rm', image)
			if ret != 0:
				log('Failed to remove image')
				return False
		return True

	def findDcrCont(self, tagExpr='', allowAll=False):
		ret, psOut = self.runCmd('docker', 'ps', ('', '-a')[allowAll], verbose=False)
		contList = []
		for line in psOut.splitlines()[1:]:
			if not re.search(tagExpr, line):
				continue
			contId, image = line.split()[:2]
			log(f'Container Identified: {contId} - {image}')
			contList.append(contId)
		return contList

	def getDcrCont(self, tagExpr='', allowMultiple=False):
		contList = self.findDcrCont(tagExpr)
		if not contList:
			return None
		if len(contList) == 1:
			return Container(self, contList[0])
		elif not allowMultiple:
			return None
		for i, contId in enumerate(contList):
			contList[i] = Container(self, contId)
		return contList

	def rmDcrCont(self, tagExpr=''):
		contList = self.findDcrCont(tagExpr, allowAll=True)
		for contId in contList:
			log(f'Removing: {contId}')
			ret, out = self.runCmd('docker', 'container', 'stop', contId)
			if ret != 0:
				log('Failed to stop container')
				return False
			ret, out = self.runCmd('docker', 'container', 'rm', contId)
			if ret != 0:
				log('Failed to remove container')
				return False
		return True


def followCmds(*channels, timeout=CONSOLE_TIMEOUT):
	multiChs = len(channels) > 1
	def _log(i, msg):
		log(b'[%d] %s' %(i, msg.strip()) if multiChs else msg, newline=multiChs)
	multiChs and [log(f'[{i}] Parallel Run: {ch.cmd}') for (i, ch) in enumerate(channels)]
	fds = [ch.fileno() for ch in channels]
	_fds = list(fds)
	rets = [[None, ''] if ch.mixStderr else [None, '', ''] for ch in channels]
	any([ch.verbose for ch in channels]) and log('out:')
	while _fds:
		rfds = select.select(_fds, [], [], timeout)[0]
		if not rfds:
			msg = f'Reached Timeout of {timeout} sec, Exiting...'
			log(msg)
			for fd in _fds:
				i = fds.index(fd)
				rets[i][0] = 1
				rets[i][1] += msg
				channels[i].close()
			return rets
		for fd in rfds:
			i = fds.index(fd)
			ch = channels[i]
			while ch.recv_ready():
				chunk = ch.recv(8096)
				ch.verbose and _log(i, chunk)
				ch.teeFd and ch.teeFd.buffer.write(chunk)
				rets[i][1] += chunk.decode(errors='replace')
			while ch.recv_stderr_ready():
				chunk = ch.recv_stderr(8096)
				ch.verbose and ch.verboseErr and _log(i, chunk)
				ch.teeFd and ch.teeFd.buffer.write(chunk)
				rets[i][bool(not ch.mixStderr)+1] += chunk.decode(errors='replace')
			if ch.exit_status_ready():
				rets[i][0] = ch.recv_exit_status()
				_fds.remove(fd)
				ch.verbose and ch.verboseRet and _log(i, b'ret: %d\n' %(rets[i][0]))
	return rets


class RemoteNode(Node):
	def __init__(self, host, port=22, user=None, passwd=None, keyfile=None):
		super().__init__()
		self.host = host
		self.port = int(port)
		self.user = user
		self.passwd = passwd
		self.keyfile = keyfile
		self.session = paramiko.SSHClient()
		self.session.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		self.transport = None

	def _getPasswd(self):
		return self.passwd

	def check(self, host=None, port=None, timeout=5, verbose=True):
		host = host or self.host
		port = port or self.port
		sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		sock.settimeout(timeout)
		ret = sock.connect_ex((host, port))
		sock.close()
		if ret != 0:
			verbose and log(f'{self.host}:{self.port} Error: {os.strerror(ret)}')
			ret in (111, ) and time.sleep(5) # needed on some rets
		return bool(ret == 0)

	def getIp(self, host=None):
		host = host or self.host
		return socket.gethostbyname(host)

	def login(self, timeout=2*60):
		for i in range(int(timeout/5)):
			if self.check():
				break
		if not self.check():
			log(f'Node not reachable: {self.host}')
			self.errors.append(('Ping', -1, 'Node Not Reachable'))
			return False
		kwargs = {'username': self.user}
		self.passwd and kwargs.setdefault('password', self.passwd)
		self.keyfile and kwargs.setdefault('key_filename', self.keyfile)
		try:
			self.session.connect(self.host, self.port, **kwargs)
		except Exception as exp:
			log(f'{self.host}: Login Failed: {exp}')
			self.errors.append(('SSH-Login', -1, str(exp)))
			return False
		self.transport = self.session.get_transport()
		log(f'Connected to Node: {self.host}')
		return True

	def _getChannel(self):
		(self.transport and self.transport.active) or self.login()
		channel = self.transport.open_session()
		return channel

	def runCmd(self, *cmd, cwd=None, env={}, stdin=None, timeout=CONSOLE_TIMEOUT, attempts=1, nowait=False, teeFd=None, verbose=True):
		chdir = ''
		if cwd:
			chdir += f'cd {cwd}; '
		env.update(self.env)
		defineEnvs = ''
		for name, value in env.items():
			defineEnvs += f'export {name}="{value}"; '
		cmd = ' '.join(cmd)
		cmd = chdir + defineEnvs + cmd
		verbose != None and log(f'LaunchCmd: {cmd}')
		for i in range(attempts):
			i and time.sleep(8**(i+1))
			channel = self._getChannel()
			channel.exec_command(cmd)
			channel.cmd = cmd
			channel.verbose = verbose
			channel.teeFd = teeFd
			channel.verboseRet = channel.verboseErr = channel.mixStderr = True
			if stdin:
				channel.send(stdin)
				channel.shutdown_write()
			if nowait:
				return channel
			[(ret, out)] = followCmds(channel, timeout=timeout)
			if ret == 0:
				return ret, out
			if i+1 != attempts:
				verbose != None and log(f'RetryCmd[{i+2}]: {cmd}')
				continue
			if verbose != None:
				log(f'cmd failed: {cmd}')
				errOut = '\n'.join(out.splitlines()[-15:])
				self.errors.append((cmd, ret, errOut))
			return ret, out

	def runPy(self, funcPtr, args, *helperFuncs, cwd=None, pudo=False, env={}, timeout=CONSOLE_TIMEOUT, verbose=True, teeFd=None, nowait=False):
		chdir = ''
		if cwd:
			chdir += f'\nos.chdir("{cwd}")'
		env.update(self.env)
		defineEnvs = ''
		for name, value in env.items():
			defineEnvs += f'\nos.environ["{name}"] = "{value}"'
		defineFuncs = ''
		for fPtr in helperFuncs + (funcPtr, ):
			defineFuncs += f'\n{textwrap.dedent(dill.source.getsource(fPtr).strip())}'
		argStr = marshal.dumps(args)
		delimiter = ':=:=:'
		pycode = f'''\
import os
import sys
import time
import re
import marshal
{defineFuncs}
{defineEnvs}
{chdir}
args = marshal.loads({repr(argStr)})
ret = {funcPtr.__name__}(*args)
retStr = marshal.dumps(ret)
print('{delimiter}%s{delimiter}' %(retStr), file=sys.stderr) '''
		verbose != None and log(f'RemotePy: {funcPtr.__name__}', newline=False)
		verbose and log(f'{repr(args)}', newline=False)
		verbose == None or log('')
		channel = self._getChannel()
		channel.exec_command(f'{("", "pudo ")[pudo]}python3')
		channel.send(pycode)
		channel.shutdown_write()
		channel.cmd = f'{funcPtr.__name__}{repr(args)}'
		channel.teeFd = teeFd
		channel.verbose = verbose
		channel.verboseRet = channel.verboseErr = channel.mixStderr = False
		if nowait:
			return channel
		[(ret, stdout, stderr)] = followCmds(channel, timeout=timeout)
		retExpr = re.compile(f"{delimiter}(.*?){delimiter}")
		err = retExpr.sub('', stderr).strip()
		if 'Traceback' in err:
			err = re.sub('\n.*?module>|File "<stdin>", ', '', err)
			err = re.sub(r'line (\d+)', lambda m: f'line {int(m.group(1))-6}', err)
			log(f'{"="*40}\n'
				+ '\n'.join(['%02d: %s' %(e[0]+1, e[1]) for e in enumerate(defineFuncs.splitlines()[1:])]) + '\n'
				+ f'{"-"*40}\n' + f'{err}\n' + f'{"="*40}'
			)
			expType, msg = re.search(r'(\w+): (.*)', err).groups()
			traceback = '] ['.join(re.findall(r'in (\w+)', err))
			remoteException = __builtins__.get(expType, 'Exception')(f'[{traceback}] {msg}')
			raise remoteException
		retStr = retExpr.search(stderr).group(1)
		ret = marshal.loads(eval(retStr))
		verbose and log(f'ret: {ret}')
		return ret

	def runParallelCmds(self, *cmds, cwd=None, env={}, timeout=CONSOLE_TIMEOUT, verbose=True):
		channels = []
		for cmd in cmds:
			channels.append(self.runCmd(cmd, env=env, cwd=cwd, verbose=verbose, nowait=True))
		rets = followCmds(*channels, timeout=timeout)
		for ret, out in rets:
			if ret != 0 and verbose != None:
				log(f'cmd failed: {cmd}')
				errOut = '\n'.join(out.splitlines()[-15:])
				self.errors.append((cmd, ret, errOut))
				break # tobe fix: notifying only first occured error
		return rets

	def runParallelPys(self, *funcs, cwd=None, pudo=False, env={}, timeout=CONSOLE_TIMEOUT, verbose=True):
		channels = []
		for (funcPtr, args, *helperFuncs) in funcs:
			channels.append(self.runPy(
				funcPtr, args, *helperFuncs, cwd=cwd, env={}, verbose=verbose, nowait=True
			))
		return followCmds(*channels, timeout=timeout)

	def sendFile(self, localFilepath, remoteFilepath):
		fd = open(localFilepath)
		content = fd.read()
		fd.close()
		return self.writeFile(remoteFilepath, content)

	def getFile(self, remoteFilepath, localFilepath):
		content = self.readFile(remoteFilepath)
		fd = open(localFilepath)
		fd.write(content)
		fd.close()

	def reboot(self, timeout=15*60):
		log('Rebooting the Node')
		ret, out = self.runCmd('pudo', 'reboot', verbose=None)
		if ret not in (-1, 0):
			log('Failed to reboot the Node')
			return False
		# wait for node down
		ret = False
		time.sleep(5)
		for i in range(int(timeout/5)):
			if not self.check(verbose=False):
				log('Node went down')
				ret = True
				break
			log('Waiting for Node to go down')
			time.sleep(5)
		if not ret:
			log('Node did not went down even after timeout')
			return False
		# wait for node up
		for i in range(int(timeout/5)):
			if self.check(verbose=False):
				log('Node got up after reboot')
				time.sleep(5)
				return self.login()
			log('Waiting for Node')
			time.sleep(5)
		log('Node did not got up even after timeout')
		return False

	def getHomeDir(self):
		if not self.homeDir:
			ret, out = self.runCmd('pwd', verbose=None)
			self.homeDir = out.strip()
		return self.homeDir

	def getHostname(self):
		if not self.hostname:
			ret, out = self.runCmd('hostname', verbose=None)
			self.hostname = out.strip()
		return self.hostname

	def close(self):
		self.transport and self.transport.close()
		self.session and self.session.close()

	def __del__(self):
		self.close()


# lockhart node utilities
class LockhartNode(RemoteNode):
	def __init__(self, host, port=22, user=None, passwd=None, proxyIp=None):
		user = user or 'madkasul'
		sshDir = f'{os.environ.get("HOME", ".")}/.ssh'
		keyfile = f'{sshDir}/{user}_id_rsa'
		if not os.path.exists(keyfile):
			user = 'madkasul'
			keyfile = f'{sshDir}/id_ecdsa'
		super().__init__(host=host, port=port, user=user, passwd=keyfile)
		self.proxyIp = proxyIp or 'lockhart-login1.amd.com'
		self.proxySession = paramiko.SSHClient()
		self.proxySession.load_system_host_keys()
		self.proxySession.set_missing_host_key_policy(paramiko.AutoAddPolicy())
		self.proxyTransport = None
		self.proxyTunnel = None
		self.proxyEnv = {}
		self.env.update({
			'http_proxy': 'http://172.23.0.2:3128/',
			'https_proxy': 'http://172.23.0.2:3128/',
		})

	def proxyCheck(self):
		return super().check(host=self.proxyIp)

	def proxyLogin(self):
		if not self.proxyCheck():
			log(f'Proxy not reachable: {self.proxyIp}')
			return False
		self.proxySession.connect(self.proxyIp, username=self.user, key_filename=self.passwd)
		self.proxyTransport = self.proxySession.get_transport()
		self.proxyTransport.set_keepalive(3600)
		log(f'Connected to Proxy: {self.proxyIp}')
		return True

	def getIp(self, host=None):
		return super().getIp(host=self.proxyIp)

	def check(self):
		channel = self.proxyTransport.open_session()
		channel.exec_command(f'nc -zvw5 {self.host} 22')
		ret = channel.recv_exit_status()
		return bool(ret == 0)

	def createProxyTunnel(self):
		localAddr = (self.proxyTransport.sock.getsockname()[0], 22)
		remoteAddr = (self.host, 22)
		self.proxyTunnel = self.proxyTransport.open_channel("direct-tcpip", remoteAddr, localAddr)

	def login(self):
		if not self.proxyLogin():
			return False
		self.createProxyTunnel()
		return super().login(self.host, username=self.user, key_filename=self.passwd, sock=self.proxyTunnel)

	def getPipCmd(self):
		return ('pudo', 'pip3', '--proxy', self.env['http_proxy'])

	def close(self):
		self.proxyTunnel and self.proxyTunnel.close()
		self.proxyTransport and self.proxyTransport.close()
		self.proxySession and self.proxySession.close()
		super().close()

	def __del__(self):
		self.close()


class Mi300Node(RemoteNode):
	def __init__(self, host, port=22, user=None, passwd=None, keyfile=None):
		user = user or 'madkasul'
		sshDir = f'{os.environ.get("HOME", ".")}/.ssh'
		keyfile = f'{sshDir}/{user}_id_rsa'
		if not os.path.exists(keyfile):
			user = 'madkasul'
			keyfile = f'{sshDir}/id_ecdsa'
		super().__init__(host=host, port=port, user=user, keyfile=keyfile)


class TrexNode(RemoteNode):
	def __init__(self, host, port=22, user=None, passwd=None):
		keyfile = f'{os.environ.get("HOME", ".")}/.ssh/trex_id_rsa'
		super().__init__(host=f'jenkins-{host}', port=port, user='jenkins', keyfile=keyfile)


def getNode(nodeName=None, user=None):
	if not nodeName or nodeName == 'localhost':
		node = Node()
		node.installPudo()
		return node
	elif mtch:=re.search(r'(.*?):(\w+):(.*)', nodeName):
		host, user, passwd = mtch.groups()
		node = RemoteNode(host=host, user=user, passwd=passwd)
	elif mtch:=re.search(r'^trex-', nodeName):
		node = TrexNode(host=nodeName)
	elif mtch:=re.search(r'^conductor-(.*)', nodeName):
		node = Mi300Node(host=mtch.group(1), user=user)
	elif mtch:=re.search(r'(x\d+c\ds\db\dn\d)', nodeName):
		node = LockhartNode(host=mtch.group(1), user=user)
	else:
		cacheFile = os.path.expanduser('~/.cache/nodes')
		if not os.path.exists(cacheFile):
			cacheDir = os.path.dirname(cacheFile)
			os.path.isdir(cacheDir) or os.makedirs(cacheDir)
			nodes = {}
		else:
			with open(cacheFile, 'r') as fd: nodes = json.load(fd)
		if nodeName not in nodes:
			nodes[nodeName] = jenkins.Jenkins().getNodeCreds(nodeName)
			with open(cacheFile, 'w') as fd: json.dump(nodes, fd, indent=2)
		host, port, user, passwd = nodes[nodeName]
		node = RemoteNode(host=host, port=port, user=user, passwd=passwd)
		if not node.check():
			nodes[nodeName] = jenkins.Jenkins().getNodeCreds(nodeName)
			host, port, user, passwd = nodes[nodeName]
			node = RemoteNode(host=host, port=port, user=user, passwd=passwd)
			with open(cacheFile, 'w') as fd: json.dump(nodes, fd, indent=2)
	node.name = nodeName
	node.login() and node.installPudo()
	return node
