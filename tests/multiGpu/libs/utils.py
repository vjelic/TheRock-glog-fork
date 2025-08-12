#!/usr/bin/python3
import os
import re
import sys
import json
import time
import base64
import logging
import traceback


class Singleton(type):
	_instances = {}
	def __call__(cls, *args, **kwargs):
		if cls not in cls._instances:
			cls._instances[cls] = super(Singleton, cls).__call__(*args, **kwargs)
		return cls._instances[cls]


def _callOnce(funcPointer):
	def funcWrapper(*args, **kwargs):
		if 'ret' not in funcPointer.__dict__:
			funcPointer.ret = funcPointer(*args, **kwargs)
		return funcPointer.ret
	return funcWrapper


@_callOnce
def getLogger(level=logging.INFO, logFile=None):
	logger = logging.getLogger()
	logger.setLevel(level)
	formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
	cHandler = logging.StreamHandler(sys.stdout)
	cHandler.setLevel(logging.DEBUG)
	cHandler.setFormatter(formatter)
	logger.addHandler(cHandler)
	if logFile:
		fHandler = logging.FileHandler(logFile)
		fHandler.setLevel(level)
		fHandler.setFormatter(formatter)
		logger.addHandler(fHandler)
	return logger


def log(msg, newline=True):
	if isinstance(msg, bytes):
		msg = msg.decode('utf-8', errors='ignore')
	msg = msg + ('', '\n')[newline]
	sys.stdout.write(msg) and sys.stdout.flush()


def logExp(e):
	(tbHeader, *tbLines, error) = traceback.format_exception(type(e), e, e.__traceback__)
	log(f'{error}{tbHeader}{"".join(tbLines)}')


def runCmd(*cmd, cwd=None, env={}, stdin=None, nowait=False, verbose=True):
	import subprocess
	if verbose != None:
		cwdStr = f'cd {cwd}; ' if cwd else ''
		envStr = ''
		for key, value in env.items():
			envStr += f"{key}='{value}' "
		log(f'RunCmd: {cwdStr}{envStr}{" ".join(cmd)}')
	# launch process
	cmdEnv = os.environ.copy()
	env and cmdEnv.update(env)
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
	verbose and log('out:')
	out = ''
	chunk = None
	while chunk != b'':
		chunk = process.stdout.read(1)
		verbose and sys.stdout.buffer.write(chunk) and sys.stdout.flush()
		out += chunk.decode(errors='replace')
	# handling return value
	ret = process.wait()
	if ret != 0 and verbose != None:
		log(f'cmd failed: {" ".join(cmd)}')
		verbose or log(f'err: {out}')
	verbose and log(f'ret: {ret}')
	return ret, out


def request(method, url, allowCodes=(), ignoreExp=False, verbose=False, **kwargs):
	# /usr/lib/python3/dist-packages/requests/api.py
	# method: GET, POST, DELETE, OPTIONS
	# kwargs: headers, json, data, params, cookies
	import requests
	from requests.exceptions import ConnectionError, Timeout, RequestException
	verbose and log(f'{method}: {url}')
	kwargs and verbose and log(f'\t{kwargs}')
	allowCodes = (200, *allowCodes)
	exp = resp = None
	for i in range(3): # retry for 3 times
		try:
			resp = requests.request(method, url, **kwargs)
		except (ConnectionError, Timeout, RequestException) as e:
			(verbose != None) and logExp(e)
			exp = e
		if resp and resp.status_code in allowCodes:
			break
		resp and (verbose != None) and log(f'{method}: {url} => [{resp.status_code}]{resp.reason}')
		(verbose != None) and log(f'Re-Trying...')
		time.sleep(2**(i+1))
	if exp and not ignoreExp:
		raise exp
	if resp:
		if verbose or (verbose == False and resp.status_code not in allowCodes):
			log(f'{method}: {url} => [{resp.status_code}]{resp.reason}')
		if re.search(r'^[\[\{].*[\]\}]$', resp.text, flags=re.DOTALL):
			resp.jsonData = resp.json()
			verbose and log(f'Json: {json.dumps(resp.jsonData, sort_keys=True, indent=2)}')
		else:
			resp.jsonData = None
			verbose and log(f'Text: {resp.text}')
	return resp


@_callOnce
def nproc():
	return int(runCmd('nproc', verbose=None)[1])


@_callOnce
def getGithubToken():
	base64Token = 'N2dsYWFDa1lJR29JeFJIUUx1azRDWGJIY3NIUm1sMXhiNDFx'
	return base64.b64decode(base64Token).decode()


@_callOnce
def getRocmInternalGPG():
	base64GPG = '''\
mQENBGMx+g4BCACy93vlsgmNaqjPkhYnwLs6sAq/V5vz5NQ/nigioYf2AN2nh44J0z1waShUESh5
F+sYR741Y2ijs+nKmIh/DAF4Wqhz3SLnyktuv8QKc8E0bi5Qs/wGK7SBIuI7KUK+M/QV75krlz79
9S0sUJNwnvuYJt9m0zAIn5O1/HZKa7SubLcWnWJmAMyeMMORrbTnP9qyRXAb+cyGRiF4lwndsaTA
RYWHd+MkLU0duFRPN3UtfqHwoX926BvJ/NNFLsIksC/mQ8Empb31uEyieqQIsNxsGduh78/WyorT
uOJFuHi7pkQvew3sFDVAVQs3ivgJNiY/PKAH9vkbubQoYfbVp5N5ABEBAAG0O2NvbXB1dGUtYXJ0
aWZhY3RvcnkgKFNpZ25pbmcga2V5KSA8amVua2lucy1jb21wdXRlQGFtZC5jb20+iQE5BBMBAgAj
BQJjMfoOAhsDBwsJCAcDAgEGFQgCCQoLBBYCAwECHgECF4AACgkQrDRNJV5IxxRQMgf/ftGSPnnc
eKJcAoaql1LX7eAPbCZg/yo6kN5JJ1LoPni/o2l1K/hUxY5CjKYDFa7Q2QAxO/bB/i5RsnmA6tnm
dv9OPFQ3fjL3K6ZW1rak+O/NjHiDjd0BlFaq9Lls9KICipIwiphHDNuC3hffxG3xoSttM6pEXHm6
uqD3kAieS+mgXzi8dN2iPsfuRDT8yMGLO17HxSHVq3be3VoOvIVbuQeBkfA3WyyC9jXPe23TM2HA
HH/VjvAYOoYgqWQWb0xfAdEEL5AFn6fydx/bacy+dfbCX11dMX30cw8nw9FZILHZocf7xEaSshvV
+BMfj2JPlGRou7or7NPer8Agn+FSrLkBDQRjMfoOAQgA7384FMFLTYqnHYyCoh2g6mClgMesohNW
KaMPrjGYk8uB3XSl4tfF/CEwUGPqdSU1USapw0HZ5B34C8BLqXOcMYjTtkYfyJ7oYasKOKuNlCY6
Po6zG4dBQVRObomafIKsVwbJflpzPz6STwaBdT4BZnvTvmLa3z6d6GObZHFXMPjTAYIuXLspjmqH
bIASKBKt7EEm93v8muqiUSAlFEtupLJeebP7xEMxoKhnAdq68aoqIEEYvHqOa1K4TmPSaxDiWKYw
TuVUzkowsr7M6zDOPx/0S6qXFYcQCinRUlyWhtJuQhbAAMcsx03G/H4R8o1OvoTyGrA0Ry90PA1d
eMQ0eQARAQABiQEfBBgBAgAJBQJjMfoOAhsMAAoJEKw0TSVeSMcUsZgIAJc0bD8wNfVxPlTXJc25
9oPhdfmLh+94Luj21qMfoew0GG7q16nnbsgQ09ckUDKmeSiMzYsj0efSvGfkG25LqQBbZaYO/hH2
rHSO0CrFE3SeO4AwaBgQw5tyY0ByjfufwheOxy1Ee4Gw+PX+a/pf1agGnXfVptzZXKE57rZeec5z
AGvkDHpQfcbQZex1B93V7FGYAsElm5Ss7JwWVEhVtn8BtGpHAOVIVm0OF59cFgb4iP++Cm1MS2D+
yxuwXzaAkmyDPTrBUEjUIm8eiXCfT0nQ3BAfArotwXkcSuI9z3PDSveQbdoWZzK9ZWnG9oFvR7SJ
XqVUdKjmLN1uvmL4BlU='''
	return base64.b64decode(base64GPG)


@_callOnce
def getGerritPvtKey():
	basePvtKey = '''\
LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFcEFJQkFBS0NBUUVBd2F1Qjh2ZER4
dW9DRG1qY2NrMy82aklhU1pYMyttVVhrWGdPK2U4VkhMVkF5dytkCmpwc1dBOFR0NCtacS9NWmhj
SVB0b05jUVMwN25lWnpMbW1lQVh1NUlyWVpCUFFZQ1FPSkJHWXR3UE1CRjZxOXQKcHplUEJnbnVN
YURrcDMrRzgwdGkvaEdkSmFPMmpXTE9DNlNLNzh1eTY1REJKZ0FKT3Jnb2drS1JkYUI5a3VWbApM
c1A5QzBQeE9OYzEyVWd1MHliYWp0TEJtVTJjNlEzbkpEeTAvQ0JuWFo5cExaUmZDMkFWTnVGMngy
V25wbURTCjRROUVmZk1UREhMWkgvN2JyRnNGa2xVWjYrUkM2YW5Gc3FtazJ4UnBweTVFY3pNUmZt
Qi9UdmtKSStzMnY0WnYKZXZTbEdHZ0RTZm5GUktrMWk2WXQ2Nzh0Mkg2ZW5BZjZHNU5zZHdJREFR
QUJBb0lCQUJUN082elMxT2pyMlNVdQpmeE56RjlLTGN3V2QxYXV1NEFyR2N2am95ZVMrVGpLeGtt
UXNzUW5mZjlZODFFSm1TNUFnK3RGOSt5bnRkbTVhCmFrUmtDaWcrc0dqOExuMHA5WHlLQm50NSs4
TFpJYm4zSDI0S090aHdvdm1GY01Ba3RMNE80TDZkc2VTdUE4ejEKYzFVWGttWEFMN1lOako5TlNi
S3UyTlNqMlpaZ2lHRmc5c0VKbUlTWWtOOHYySFA2c0trbXk1MXB1ZzFIYW5Ecwp2RXNHRWsyWWlw
ckI0a2Q4blNnZlpPcUJnQmRYUDZCamlLRTNtN29Nb2lzVkNoaHZaaEgxQ3FLaHZjM09TbkcyCjk5
ZWw4RXMzZnNTblY4ZGMwTUpwekZjMDc5Wk5CTVFGaTh5K3pYRkdVN3MxVzNIMWZvVmdpVDh4V2lP
aDd6VysKaVNxWExJRUNnWUVBN1kwMGJyaVE3TW5QWUYxRzNmMEE4NlYrU2ZOT29ocDk2WXVwcHRV
MHZlcmxwT1J1WkhxZQpJN3Z6REpQZ3B6WE9KSzRJMjRGTmVLR1owZ3NlUTNJT2phQkx3WFJJQjZG
SEJlbWdPenVRRllxbi8vYTRRb0FUClhnaGtDeWQ2M090SkliYW5vcDN2Wk1lQ3lNSGxmVTdVZmli
dk9jL0NuYUR5NWM1YWQwT2xDOGNDZ1lFQTBMWGkKM0NQNmVKaUhReUVOK2ZuZ0ZrTXE2cjJtTGZR
b2FNbThDbUNLbGQ4VXJVd3M4VkxOcm1BaTNVejFMZHljNHByRgppblR6RmwyUHcyVXB0UkZCanNG
aUI3TGd4MCtEczQyZG1xc1oyYkZadkhnakQveDZJRHdQUDNuTXFuSWw4Qk5RCnZxV0xUVXNpZlBi
T0Y0WjBnRElnSkxrWk4xYXlJS2hDcmUwZXVkRUNnWUVBcWtZTXoxQjhrVDRXNTN2MDBDb0sKQkpz
YmF1Wjc5cllHaXVFUk9nU1pTWWlXRXh1cUJWdmUvcjQ1K1VvR1BkVFRibmRRNGdaTkFhclVGenJn
OW5kSwo5emx2RTd2RjViSTB0b2cvMGpWZmtoRlJXcWYrYTZ4aU5ZVE9NVENiWUw5R0xHUkF4TTl3
U1V5NDhpNEowVWd3CkNEemdQUkF1NzgzdVRjc2NEV0R2YlFFQ2dZQXhMSG1MNW9vditiZjh6Ly9z
QXJ5U1lqYnRZY3VTampFckowUy8KcVNsZDBGYWQwaEhRdGZLeUFBS1c0M2ZzMjBxM2RVSFBzbWhI
djdtTWp2dzVwaHd0RjFFU2dVbkdpK3g2MUlYcQptQithRTlnUnVMaUNIcmxqZU9NYTBJYXhMZjNV
UjZqQmtsMTAwNXdIbDFyTlhpZDZ3TlNqOGx5SGxreVh0eTBtCnIzU0swUUtCZ1FEYlNGYUppT1A2
eUhBdFNEVElIcHNoRzVoZlBSL3lvSWhxb1dRVE1RbjU1NW5MelBLNU1POW4KRjVYcDZmYXJsVU8v
Q1dxKy9BbmVDMHRGbWN6bHEvU0xOTS9hdGVhWnl1Sk9WRnlMb1ZxOStSZG1FM0R3WTltTQpkSDMw
QWFLT0dzZWo1akJGNEltSjRGbTVFWlpCcTV1SDVaTTUvazlWUzBGaHBQUGtuYWs4Ync9PQotLS0t
LUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQo='''
	return base64.b64decode(basePvtKey)


@_callOnce
def getGithubEmuPvtKey():
	base64Token = '''\
LS0tLS1CRUdJTiBPUEVOU1NIIFBSSVZBVEUgS0VZLS0tLS0KYjNCbGJuTnphQzFyWlhrdGRqRUFB
QUFBQkc1dmJtVUFBQUFFYm05dVpRQUFBQUFBQUFBQkFBQUFNd0FBQUF0emMyZ3RaVwpReU5UVXhP
UUFBQUNEVkNxMVhDdFlENFNWVktobXRhMFl2bGVITDB0alV3ZW03NmIyTjVzNi9EQUFBQUtBc2xs
K3FMSlpmCnFnQUFBQXR6YzJndFpXUXlOVFV4T1FBQUFDRFZDcTFYQ3RZRDRTVlZLaG10YTBZdmxl
SEwwdGpVd2VtNzZiMk41czYvREEKQUFBRURFMkdTWmNYOFFydTg1R0tNcjF4K0p4ZVU1NkdubmFj
c29XMEN0Q3FaRW5OVUtyVmNLMWdQaEpWVXFHYTFyUmkrVgo0Y3ZTMk5UQjZidnB2WTNtenI4TUFB
QUFGbUV4TG5KdlkyMWZaR1YyYjNCelFHRnRaQzVqYjIwQkFnTUVCUVlICi0tLS0tRU5EIE9QRU5T
U0ggUFJJVkFURSBLRVktLS0tLQo='''
	return base64.b64decode(base64Token)


@_callOnce
def getCommonUser():
	from cryptography.fernet import Fernet
	username = 'a1_rocm_staging'
	password = base64.b64decode(b'RmM1QzlzNSMzMDE0MiQk').decode()
	return username, password


def syncGitRepo(url, branch, cwd='.', pvKey=None, verbose=False):
	log(f'Syncing Git repo: {url}')
	if not os.path.isdir(cwd):
		os.makedirs(cwd)
	repoBaseName = re.search(r'.*/([\w-]+)', url).group(1)
	repoPath = os.path.join(cwd, repoBaseName)
	env = {}
	pvKey and env.update({'GIT_SSH_COMMAND': f'ssh -i {pvKey} -o StrictHostKeyChecking=no -o IdentitiesOnly=yes'})
	ret, out = runCmd('git', '-C', repoBaseName, 'status', '--porcelain', cwd=cwd, verbose=None)
	if ret != 0:
		ret, out = runCmd('git', 'clone', url, cwd=cwd, env=env, verbose=verbose)
		if ret != 0:
			log(f'out:\n{out}')
			return None
	runCmd('git', 'stash', cwd=repoPath, verbose=verbose)
	runCmd('git', 'remote', 'set-url', 'origin', url, cwd=repoPath, env=env, verbose=verbose)
	if re.match(r'^[a-f\d]*$', branch): # if commit id requested
		ret, out = runCmd('git', 'fetch', 'origin', branch, cwd=repoPath, env=env, verbose=verbose)
		if ret != 0:
			log(f'out:\n{out}')
			return None
		ret, out = runCmd('git', 'checkout', branch, '-B', f'privateCheckout', cwd=repoPath, env=env, verbose=verbose)
		return repoPath
	ret, out = runCmd('git', 'fetch', 'origin', branch, cwd=repoPath, env=env, verbose=verbose)
	if ret != 0:
		log(f'out:\n{out}')
		return None
	runCmd('git', 'checkout', f'origin/{branch}', '-B', branch, cwd=repoPath, env=env, verbose=verbose)
	return repoPath


def splitBuildLink(buildUrl):
	return re.search(r'([\w\.-]+)/*(\d*)/*$', buildUrl).groups()


def getBuildDockers(buildUrl, expr='', verbose=False):
	url = 'compute-artifactory.amd.com:5000'
	namespace = 'rocm-plus-docker'
	job, num = splitBuildLink(buildUrl)
	resp = request(
		method='GET',
		url=f'https://{url}/v2/{namespace}/{job}/tags/list',
		auth=getCommonUser(),
		verbose=verbose,
	)
	cExpr = re.compile(f'{num}[-_].*?{expr}')
	matches = filter(cExpr.search, resp.jsonData['tags'])
	dockers = tuple(map(lambda e: f'{url}/{namespace}/{job}:{e}', matches))
	dockers or log(f'No Matching Docker Found for expr: {expr}')
	return dockers


def getIvPromotedDkms(skipDays=7):
	mainline = 'compute-rocm-dkms-no-npi-hipclang'
	resp = request('GET',
		f'http://mlseqa-portal.amd.com:8000/IVDetails/GetLKGIVBuild/{mainline}',
		params={
			'result_format': 'json',
		},
	)
	assert resp.status_code in (200, ), 'Failed to Fetch IV promoted build'
	publishDate = resp.jsonData['Report_Published_Date']
	diffTime = time.time() - time.mktime(time.strptime(publishDate, '%Y-%m-%d'))
	if diffTime < (60*60*24*skipDays):
		return None
	buildUrl = f'http://rocm-ci.amd.com/job/{mainline}/{resp.jsonData["ROCm_Build"]}/'
	# get dkms version
	resp = request('GET', buildUrl)
	assert resp.status_code in (200, ), 'Failed to fetch ROCm Build Details'
	dkmsVersion = re.search(r'(:?Linux Core Build Number|Mesa UMD Build Number):(\d+)', resp.text).group(2)
	assert dkmsVersion, 'Failed to extract dkms version'
	log(f'Last IV promoted dkms version: {dkmsVersion}')
	return dkmsVersion


def parseManifest(fd):
	import xml.etree.ElementTree
	tree = xml.etree.ElementTree.parse(fd)
	root = tree.getroot()
	remotes = {}
	for remote in root.findall('remote'):
		remotes[remote.attrib['name']] = remote.attrib['fetch']
	default = root.find('default').attrib
	manifestDict = {}
	for project in root.findall('project'):
		project.attrib['remote'] = f'{remotes[project.attrib.get("remote", default["remote"])]}/{project.attrib["name"]}'
		manifestDict[project.attrib['name']] = project.attrib
		if 'path' in project.attrib:
			path = os.path.basename(project.attrib['path'])
			if path not in manifestDict:
				manifestDict[path] = project.attrib
	return manifestDict
