#!/usr/bin/python3
import os
import re
import io
import sys
import time
import json

from . import utils
log = utils.log


class DockerContainer(object):
	def __init__(self, image):
		self.image = image
		self.contId = ''

	def pull(self):
		for i in range(3):
			ret, out = utils.runCmd('docker', 'pull', self.image)
			errExpr = 'Failed to fetch|Transaction failed|Connection failed'
			if ret == 0 or not re.search(errExpr, out):
				break
			log('docker-pull: Failed due to network issue')
			log('Retrying after 2min...')
			time.sleep(120)
		return bool(ret == 0)

	def run(self, *extraArgs, env={}, volumes={}, cwd=None):
		cmd = ['docker', 'run', '--tty', '--detach',
			'-u', f'{os.getuid()}:{os.getgid()}',
		]
		for name, value in env.items():
			cmd += ['-e', f'{name}="{value}"']
		for lpath, rpath in volumes.items():
			cmd += ['-v', f'{lpath}:{rpath}']
		ret, out = utils.runCmd(*cmd, *extraArgs, self.image, cwd=cwd)
		if ret == 0:
			self.contId = re.search(r'(.{12}).*?$', out).group(1)
		return bool(ret == 0)

	def runCmd(self, *cmd, cwd=None, env={}, **kwargs):
		contCmd = ''
		for name, value in env.items():
			contCmd += f'export {name}="{value}"; '
		if cwd:
			contCmd += f'cd {cwd}; '
		contCmd += ' '.join(cmd)
		return utils.runCmd('docker', 'exec', self.contId, 'bash', '-c', contCmd, **kwargs)

	@utils._callOnce
	def getOsDetails(self):
		ret, out = self.runCmd('cat', '/etc/os-release')
		return dict(re.findall(r'(\w+)="?([^"\n]+)', out))

	def stop(self):
		log(f'Stoping: {self.contId}')
		ret, out = utils.runCmd('docker', 'container', 'stop', self.contId)
		if ret != 0:
			log('Failed to stop container')
			return False
		return True

	def remove(self):
		self.stop()
		log(f'Removing: {self.contId}')
		ret, out = utils.runCmd('docker', 'container', 'rm', self.contId)
		if ret != 0:
			log('Failed to remove container')
			return False
		return True

	def __del__(self):
		self.contId and self.remove()
