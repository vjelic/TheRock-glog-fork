#!/usr/bin/python3
import os
import re
import io
import sys
import time
import json

from . import utils
log = utils.log

# https://www.jenkins.io/doc/book/using/remote-access-api/
class Pipeline(object):
	def __init__(self, url, jnObj):
		self.jnObj = jnObj
		self.job, self.build = utils.splitBuildLink(url)
		self.url = f'job/{self.job}/{self.build}'
		self.fullUrl = f'{jnObj.server}/{self.url}'
		self.blueOceanUrl = f'{jnObj.server}/blue/organizations/jenkins/{self.job}/detail/{self.job}/{self.build}/pipeline'
		self.console = f'{self.fullUrl}/consoleText'

	def setName(self, displayName=None, verbose=False):
		resp = self.jnObj._configSubmit(
			self.url,
			displayName=displayName,
			verbose=verbose,
		)
		log(f'Pipeline name update: {resp.reason}')
		return resp

	def setDesc(self, description, append=True, verbose=False):
		config = self.jnObj._configGet(self.url, 'displayName', 'description')
		currDesc = config['description'] or ''
		if append:
			description = currDesc + '<br>' + description
		resp = self.jnObj._configSubmit(
			self.url,
			displayName=config['displayName'],
			description=description,
			verbose=verbose,
		)
		log(f'Pipeline Description update: {resp.reason}')
		return resp

	def getArtifact(self, path, asFd=False, verbose=False):
		resp = self.jnObj.request('GET',
			f'{self.url}/artifact/{path}',
			verbose=verbose,
		)
		return io.BytesIO(resp.content) if asFd else resp.content

	def getManifest(self, verbose=False):
		fd = self.getArtifact('manifest.xml', asFd=True)
		return utils.parseManifest(fd)



class Jenkins(metaclass=utils.Singleton):
	def __init__(self, server=None):
		self.server = os.environ.get('JENKINS_URL', f'http://{server or "rocm-ci.amd.com"}' )
		self.headers = {}
		self.cookies = {}
		self.loggedin = False

	def request(self, method, url, *args, **kwargs):
		args = (method, f'{self.server}/{url}', *args)
		resp = utils.request(*args, **kwargs)
		if resp.status_code in (401, 403):
			self.login(verbose=kwargs.get('verbose', False))
			resp = utils.request(*args, **kwargs)
		return resp

	def getCreds(self):
		from cryptography.fernet import Fernet
		username = 'jenkinscompute'
		key = b'InRhcRSNdMAmAaTfmsWU8gcXfwvmNowFbtdx98mRQnI='
		# epass = Fernet(key).encrypt(b'<password>') # for encryption
		epass = b'gAAAAABnv-6Co1FdxkurllFwTHZUNaM6qjAfitBEDVhfbbH7z9GYPNUvEtK2mY0KEpA1Fi2QNtEq15i2ZWYKu09c6AQYsW7Qh4nBU5E8kvWBQAMs9wpGR1I='
		password = Fernet(key).decrypt(epass).decode()
		return (username, password)

	def login(self, verbose=False):
		self.auth = self.getCreds()
		for i in range(6):
			resp = utils.request('GET',
				f'{self.server}/crumbIssuer/api/json?',
				auth=self.auth,
				verbose=verbose,
			)
			if resp.status_code in (200, ):
				break
			log(f'Jenkins Login Failed, Trying again - [{i+1}]')
			time.sleep(2**(i+1))
		log(f'Jenkins Login Success')
		self.headers[resp.jsonData['crumbRequestField']] = resp.jsonData['crumb']
		self.cookies.update(resp.cookies)
		self.loggedin = True

	def logout(self, verbose=False):	# just for testing purpose
		resp = self.request('GET',
			'logout/api/json?',
			verbose=verbose,
		)
		self.cookies=resp.cookies
		log(f'Jenkins Logout Success')

	def _getDetails(self, url, *data, verbose=False):
		params = {'tree': ','.join(data)} if data else None
		resp = self.request('GET',
			f'{url}/api/json?',
			params=params,
			verbose=verbose,
		)
		details = resp.jsonData
		details.pop('_class')
		if len(details) == 1:
			return details.popitem()[1]
		return details

	def _configGet(self, url, *config, verbose=False):
		params = {'tree': ','.join(config)} if config else None
		resp = self.request('GET',
			f'{url}/api/json?',
			params=params,
			verbose=verbose,
		)
		config = resp.jsonData
		config.pop('_class')
		if len(config) == 1:
			return config.popitem()[1]
		return config

	def _configSubmit(self, url, verbose=False, **config):
		self.loggedin or self.login()
		data = {'json': json.dumps(config)} if config else None
		return self.request('POST',
			f'{url}/configSubmit',
			data=data,
			auth=self.auth,
			headers=self.headers,
			cookies=self.cookies,
			allowCodes=(500,),
			verbose=verbose,
			ignoreExp=True,
		)

	def getNodes(self, **kwargs):
		resp = self.request('GET',
			f'computer/api/json',
			params={
				'tree': f'computer[{",".join(kwargs.keys())}]',
				'depth': 5,
			},
		)
		assert resp.status_code in (200, ), 'Failed to fetch get nodes'
		nodes = resp.jsonData['computer']
		for key, value in kwargs.items():
			expr = re.compile(str(value))
			_nodes = []
			for node in nodes:
				if key not in node:
					log(f'{key}: not avaliable')
					return None
				expr.search(str(node[key])) and _nodes.append(node)
			nodes = _nodes
		nodes = list(map(lambda node: node['displayName'], nodes))
		log(f'Filtered Nodes: {nodes}')
		return nodes

	def getNodeCreds(self, node):
		from xml.etree import ElementTree
		self.loggedin or self.login()
		resp = self.request('GET',
			f'computer/{node}/config.xml',
			auth=self.auth,
			headers=self.headers,
			cookies=self.cookies,
		)
		# Nodes without Jenkins agents and with env[CQE_NODE_CREDS]
		if ncMtch := re.search(r'>(NODECREDS:.*?)<', resp.text):
			nodeCreds = ncMtch.group(1)
			if mtch := re.search(r'NODECREDS:(.*?):(\d+):(.*?):([^<]*)', nodeCreds):
				host, port, user, passwd = mtch.groups()
				port = int(port)
			elif mtch := re.search(r'NODECREDS:(.*?):(.*?):([^<]*)', nodeCreds):
				host, user, passwd = mtch.groups()
				port = 22
			else:
				raise Exception(f'Failed to fetch env[CQE_NODE_CREDS]: {nodeCreds}')
			return (host, port, user, passwd)
		# Nodes with Jenkins agents
		credentialMap = {
			'c98bda51-6ed2-4750-b1d3-6d217fd775fd': ('jenkins', 'atitech'),
			'jenkins-node-ssh-key-creds': ('jenkins', 'atitech'),
		}
		launcher = ElementTree.fromstring(resp.text).find('launcher')
		host = launcher.find('.//host').text
		port = int(launcher.find('.//port').text) or 22
		credentialsId = launcher.find('.//credentialsId').text
		user, passwd = credentialMap[credentialsId]
		return (host, port, user, passwd)

	def setNodeOffline(self, node, msg):
		offline, _msg = self._configGet(f'computer/{node}', 'offline', 'offlineCauseReason')
		if not offline:
			cmd = 'toggleOffline'
		elif _msg != msg:
			cmd = 'changeOfflineCause'
		else:
			return
		if url := os.environ.get('BUILD_URL', None):
			msg += f' - {url}'
		self.loggedin or self.login()
		resp = self.request('POST',
			f'computer/{node}/{cmd}?',
			params = {
				'offlineMessage': msg,
			},
			auth=self.auth,
			headers=self.headers,
			cookies=self.cookies,
		)

	def getLkgBuild(self, job):
		jobUrl = f'job/{job}'
		details = self._getDetails(jobUrl)
		num = details['lastSuccessfulBuild']['number']
		log(f'Last Succussful Build: {job}/{num}')
		return num

	def getPipeline(self, url=None):
		url = url or os.environ.get('BUILD_URL', None)
		return Pipeline(url, self) if url else None

	def getUpstreamPipeline(self, url=None):
		pipeline = self.getPipeline(url=url)
		details = self._getDetails(pipeline.url)
		for action in details.get('actions', []):
			for cause in action.get('causes', []):
				if 'upstreamProject' in cause:
					parentUrl = f'job/{cause["upstreamProject"]}/{cause["upstreamBuild"]}'
					return Pipeline(parentUrl, self)
		return None
