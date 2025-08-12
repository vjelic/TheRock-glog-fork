import os
import sys
import time
import re
import pytest

import logging
logging.getLogger('paramiko').setLevel(logging.WARNING)
logging.getLogger('urllib3').setLevel(logging.WARNING)

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))
from libs import utils
from libs import nodelib
from libs import jenkins
log = utils.log


def pytest_addoption(parser):
	parser.addoption('--host', action='store', default=None, help='name/ip of the test machine')
	parser.addoption('--user', action='store', default=None, help='user to login to the test machine')
	parser.addoption('--dkms', action='store_true', default=False, help='to install dkms pkgs')
	parser.addoption('--rocm', action='store', default=None, help='to install rocm userspace pkgs')
	parser.addoption('--notify', action='store_true', default=False, help='sends teams notification')
	parser.addoption('--emailTo', action='store', default=None, help='sends email report to comma separated ids')
	parser.addoption('--logDir', action='store', default='', help='log directory path')
	parser.addoption('--setUpstreamMetadata', action='store_true', default=False, help='to update metadata of the upstream pipeline')


@pytest.fixture(scope='session')
def title():
	return 'ROCm_Tests'


@pytest.fixture(scope="session", autouse=True)
def cachedir(request):
	cachedir = request.config.cache._cachedir
	if not os.path.exists(cachedir):
		os.makedirs(cachedir)


@pytest.fixture(scope="session")
def host(pytestconfig):
	return pytestconfig.getoption('host') or 'localhost'


@pytest.fixture(scope="session")
def notify(pytestconfig):
	return pytestconfig.getoption('notify')


@pytest.fixture(scope="session")
def emailTo(pytestconfig):
	if emailTo := pytestconfig.getoption('emailTo'):
		return emailTo.split(',')
	return emailTo


@pytest.fixture(scope='session')
def jnObj():
	return jenkins.Jenkins()


@pytest.fixture(scope='session')
def report(notify, emailTo, host, jnObj, request):
	from libs import report
	report = report.Report()
	report.node = host
	yield report
	verdict = not(request.session.testsfailed)
	notify and report.sendMsg(verdict=verdict)
	emailTo and report.sendEmail(verdict=verdict, recipients=emailTo)


@pytest.fixture(scope='class')
def count(pytestconfig, report):
	count = None
	if pytestconfig.getoption('count') > 1:
		count = report.addTable(title='Iteration Report:')
		count.fCount = count.pCount = count.total = 0
		count.addHeader('Test', 'Fail', 'Pass', 'Total')
	yield count
	if pytestconfig.getoption('count') > 1:
		log('\n' + count.pprint())


@pytest.fixture(scope='class')
def result(jnObj, report):
	result = report.addTable(title=f'<a href="{jnObj.server}/computer/{report.node}/">{report.node}</a> Report:')
	result.addHeader('Test', 'Verdict', 'ExecTime')
	yield result
	log('\n' + result.pprint())


@pytest.fixture(scope="session", autouse=True)
def timeStamps(report):
	startTime = time.time()
	yield
	d = time.time() - startTime
	report.addFacts(EXEC_TIME=f'{int(d/3600)}h {int((d%3600)/60)}m {int(d%60)}s')


@pytest.fixture(scope="session")
def buildUrl(pytestconfig, report, jnObj):
	buildUrl = pytestconfig.getoption('rocm')
	if buildUrl:
		job, num = utils.splitBuildLink(buildUrl)
		if not num:
			num = jnObj.getLkgBuild(job)
			buildUrl = f'{buildUrl.strip("/")}/{num}'
		report.addFacts(BUILD=f'<a href="{buildUrl}">{job}/{num}</a>')
	return buildUrl


@pytest.fixture(scope='session')
def pipeline(pytestconfig, jnObj, buildUrl, report, autouse=True):
	pObj = jnObj.getPipeline()
	if pObj:
		report.addButtons(
			Pipeline=pObj.fullUrl,
			Console=pObj.console,
			BlueOcean=pObj.blueOceanUrl
		)
		if buildUrl:
			job, num = utils.splitBuildLink(buildUrl)
			pObj.setName(f'{job}/{num}')
	yield pObj
	if pObj:
		report.setPipelineDesc(pObj)
		if pytestconfig.getoption('setUpstreamMetadata'):
			upObj = jnObj.getUpstreamPipeline()
			upObj and report.setPipelineDesc(upObj)


@pytest.fixture(scope='session')
def node(pytestconfig, host, report, request, jnObj):
	href = f'<a href="{jnObj.server}/computer/{host}/">{host}</a>'
	host and report.addFacts(NODE=href)
	user = pytestconfig.getoption('user')
	node = nodelib.getNode(host, user=user)
	if node.errors:
		error = node.errors[0]
		jnObj.setNodeOffline(host, error[2])
		report.addFacts(NODE_OFFLINE=error[2])
		report.addErrors(error, title=href)
		assert not error, error[2]
	report.node = node.name = host
	for env in os.environ.get('EXTRA_ENV', '').splitlines():
		name, value = env.split('=')
		node.env[name] = value
	yield node
	report.addErrors(*node.errors, title=href)


@pytest.fixture(scope='session')
def dkms(pytestconfig, report, node, jnObj):
	if not pytestconfig.getoption('dkms'):
		return
	skipDays = 7
	if not (dkmsVersion := utils.getIvPromotedDkms(skipDays)):
		log(f'Skipping dkms upgrade as last IV published date was within {skipDays} days')
		return
	ret = node.installDkms(dkmsVersion)
	err = 'Failed to install dkms'
	if not ret:
		jnObj.setNodeOffline(node.name, err)
		report.addFacts(NODE_OFFLINE=err)
	assert ret, err


@pytest.fixture(scope='session')
def rocm(report, title, buildUrl, node, jnObj, dkms):
	if not buildUrl:
		return node.getRocmPath()
	job, num = utils.splitBuildLink(buildUrl)
	report.setTitle(f'{title}: {job} #{num}')
	report.addButtons(Build=buildUrl)
	ret = node.installRocmDev(buildUrl)
	err = 'Failed to install Rocm'
	assert ret , err
	return node.getRocmPath()


@pytest.fixture(scope='session')
def manifest(node, buildUrl, jnObj):
	if not buildUrl:
		check, update, install, info, remove = node.getPkgMngr()
		ret, out = node.runCmd(*info, 'rocm-core', verbose=None)
		jobBuild = re.search(r'APT-Sources: .*? (.*?/\d+) amd64 Packages', out).group(1)
		buildUrl = f'{jnObj.server}/job/{jobBuild}'
	pipeline = jnObj.getPipeline(buildUrl)
	manifestDict = pipeline.getManifest()
	return manifestDict


@pytest.fixture(scope='session')
def buildPkg(buildUrl, node):
	if not buildUrl:
		return None
	url = 'http://compute-artifactory.amd.com:8081/artifactory/rocm-generic-local/amd'
	job, num = utils.splitBuildLink(buildUrl)
	osDetails = node.getOsDetails()
	return f'{url}/{job}/{job}-{num}-{osDetails["VERSION_ID"]}.tar.bz2'


@pytest.fixture(scope='session')
def kfdTestDir(node, rocm):
	assert node.installPkgs('kfdtest', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def cmake(node):
	assert node.installPkgs('cmake', verbose=True)


@pytest.fixture(scope='session')
def rbtTestDir(node, rocm):
	assert node.installPkgs('rocm-bandwidth-test', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def hipsolverTestDir(node, rocm):
	assert node.installPkgs('rocblas', 'rocsolver', 'hipblaslt',
		'hipsparse', 'hipsolver-clients', verbose=True,
	)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rocalutionTestDir(node, rocm):
	assert node.installPkgs('rocblas', 'rocsolver', 'hipblaslt',
		'rocrand', 'rocalution-clients', verbose=True,
	)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rocblasTestDir(node, rocm):
	assert node.installPkgs('hipblaslt', 'rocblas-clients', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rocfftTestDir(node, rocm):
	assert node.installPkgs('hiprand', 'rocfft-clients', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rocsolverTestDir(node, rocm):
	assert node.installPkgs('rocblas', 'hipblaslt', 'hiprand', 'rocsolver-clients', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def hipsparseTestDir(node, cmake, rocm):
	assert node.installPkgs('hipsparse-clients', 'hipsparse-tests', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def hipblasTestDir(node, rocm):
	assert node.installPkgs('rocblas', 'rocsolver', 'hipblaslt',
		'hipblas-clients', verbose=True,
	)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rocrTestDir(node, rocm):
	assert node.installPkgs('rocrtst', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def hipfftTestDir(node, rocm):
	assert node.installPkgs('hiprand', 'hipfft', 'hipfft-clients', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rcclTestDir(node, rocm):
	assert node.installPkgs('rccl', 'rccl-clients', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rvsTestDir(node, rocm):
	assert node.installPkgs('rocrand', 'rocm-validation-suite', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def rocprimTestDir(node, cmake, rocm):
	assert node.installPkgs('rocprim-clients', verbose=True)
	return f'{rocm}/bin/rocprim'


@pytest.fixture(scope='session')
def rocrandTestDir(node, cmake, rocm):
	assert node.installPkgs('rocrand-clients', verbose=True)
	return f'{rocm}/bin/rocRAND'


@pytest.fixture(scope='session')
def rocthrustTestDir(node, cmake, rocm):
	assert node.installPkgs('rocthrust-clients', verbose=True)
	return f'{rocm}/bin/rocthrust'


@pytest.fixture(scope='session')
def amdsmiTestDir(node, rocm):
	assert node.installPkgs('amd-smi-lib-tests', verbose=True)
	return f'{rocm}/share/amd_smi/tests'


@pytest.fixture(scope='session')
def smiTestDir(node, rocm):
	assert node.installPkgs('rocm-smi-lib-tests', verbose=True)
	return f'{rocm}/share/rocm_smi/rsmitst_tests'


@pytest.fixture(scope='session')
def oclTestDir(node, rocm):
	assert node.installPkgs('rocm-ocltst', verbose=True)
	return f'{rocm}/share/opencl/ocltst'


@pytest.fixture(scope='session')
def profilerTestDir(node, rocm):
	assert node.installPkgs('rocprofiler-tests', verbose=True)
	return f'{rocm}/share/rocprofiler'


@pytest.fixture(scope='session')
def aqlProfilerTestDir(node, rocm):
	assert node.installPkgs('hsa-amd-aqlprofile-tests', verbose=True)
	return f'{rocm}/share/hsa-amd-aqlprofile'


@pytest.fixture(scope='session')
def tracerTestDir(node, rocm):
	assert node.installPkgs('roctracer-tests', verbose=True)
	return f'{rocm}/share/roctracer'


@pytest.fixture(scope='session')
def hipTestDir(node, cmake, rocm):
	assert node.installPkgs('hip-catch-amd', verbose=True)
	testdir = f'{rocm}/share/hip/catch_tests'
	yield testdir
	node.runCmd('pudo', 'rm', '-rf', f'{testdir}/Testing/Temporary')


@pytest.fixture(scope='session')
def hipcubTestDir(node, cmake, rocm):
	assert node.installPkgs('hipcub-clients', verbose=True)
	return f'{rocm}/bin/hipcub'


@pytest.fixture(scope='session')
def hipfortTestDir(node, rocm, manifest):
	assert node.installPkgs('rocblas', 'rocfft', 'hipfft', 'rocsparse', 'rocsolver',
		'hipblas', 'hipfort', 'openmp-extras-runtime',
		verbose=True,
	)
	repoDir = node.syncGitRepo(manifest['hipfort']['remote'],
		manifest['hipfort']['revision'],
	)
	return f'{repoDir}/test'


@pytest.fixture(scope='session')
def migraphxTestDir(node, cmake, rocm):
	assert node.installPkgs('migraphx', 'migraphx-tests', verbose=True)
	return f'{rocm}/libexec/installed-tests/migraphx'


@pytest.fixture(scope='session')
def mivisionxTestDir(node, cmake, rocm):
	assert node.installPkgs('libopencv-dev', 'mivisionx',
		'mivisionx-dev', 'mivisionx-test',
		verbose=True,
	)
	buildDir = f'{rocm}/share/mivisionx/test'
	ret, out = node.runCmd('pudo', 'cmake', '.',
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to compile'
	return buildDir


@pytest.fixture(scope='session')
def rdaTestDir(node, cmake, rocm):
	assert node.installPkgs('rocm-debug-agent-tests', verbose=True)
	buildDir = f'{rocm}/src/rocm-debug-agent-test/build'
	node.runCmd('pudo', 'mkdir', '-p', buildDir, verbose=False)
	ret, out = node.runCmd('pudo', 'cmake', '..',
		f'-DROCM_PATH={rocm}',
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to build'
	ret, out = node.runCmd('pudo', 'make',
		f'-j{node.getCpuCount()}',
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to compile'
	yield buildDir
	node.runCmd('pudo', 'rm', '-fr', buildDir)


@pytest.fixture(scope='session')
def gdbTestDir(node, rocm):
	def _setPtraceScope(node, option=True):
		node.writeFile('/proc/sys/kernel/yama/ptrace_scope',
		content=('0', '1')[option],
		pudo=True,
	)
	assert node.installPkgs('rocm-gdb-tests', verbose=True)
	buildDir = f'{rocm}/test/gdb/build'
	node.runCmd('pudo', 'mkdir', '-p', buildDir, verbose=False)
	_setPtraceScope(node, True)
	ret, out = node.runCmd('pudo', '../gdb/testsuite/configure',
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to configure'
	yield buildDir
	_setPtraceScope(node, False)
	node.runCmd('pudo', 'rm', '-fr', buildDir)


@pytest.fixture(scope='session')
def profilerSdkTestDir(node, cmake, rocm):
	assert node.installPkgs('pkg-config', 'libdw1', 'libdw-dev')
	assert node.installPkgs('rocprofiler-sdk-tests', verbose=True)
	profilerSdkTestDir = f'{rocm}/share/rocprofiler-sdk/tests'
	ret, out = node.runCmd('pudo', 'pip3', 'install',
		'--quiet', '-r', 'requirements.txt',
		cwd=profilerSdkTestDir,
	)
	assert ret == 0, 'Failed to install pip packages'
	ret, out = node.runCmd('pudo', 'cmake', '-B', 'build',
		f'-DCMAKE_PREFIX_PATH={rocm}', '.',
		cwd=profilerSdkTestDir,
	)
	assert ret == 0, 'Failed to configure rocProfilerSdkTests'
	ret, out = node.runCmd('pudo', 'cmake', '--build', 'build',
		'--parallel', '16',
		cwd=profilerSdkTestDir,
	)
	assert ret == 0, 'Failed to build rocProfilerSdkTests'
	return profilerSdkTestDir


@pytest.fixture(scope='session')
def rocsparseMatricesDir(node):
	def _getMatricesZip():
		matricesDir = 'rocsparseMatricesDir'
		os.makedirs(matricesDir, exist_ok=True)
		if not os.listdir(matricesDir):
			matricesZipFile = 'rocsparse-ut-matrices.zip'
			if not os.path.exists(matricesZipFile):
				artUrl = 'http://compute-artifactory.amd.com/artifactory/rocm-qa-test-logs/test-package'
				matricesZipUrl = f'{artUrl}/mathlibs/{matricesZipFile}'
				runCmd('wget', matricesZipUrl, '-O', matricesZipFile)
			import zipfile
			zipObj = zipfile.ZipFile(matricesZipFile, 'r')
			zipObj.extractall(matricesDir)
			zipObj.close()
		return f'{os.environ["HOME"]}/{matricesDir}/matrices'
	return node.runPy(_getMatricesZip, (), utils.runCmd)


@pytest.fixture(scope='session')
def rocsparseTestDir(node, cmake, rocm):
	assert node.installPkgs('rocsparse-clients', 'rocsparse-tests', verbose=True)
	return f'{rocm}/bin'


@pytest.fixture(scope='session')
def hipsparseMatricesDir(node):
	def _getMatricesZip():
		matricesDir = 'hipsparseMatricesDir'
		os.makedirs(matricesDir, exist_ok=True)
		if not os.listdir(matricesDir):
			matricesZipFile = 'hipsparse-ut-matrices.zip'
			if not os.path.exists(matricesZipFile):
				artUrl = 'http://compute-artifactory.amd.com/artifactory/rocm-qa-test-logs/test-package'
				matricesZipUrl = f'{artUrl}/mathlibs/{matricesZipFile}'
				runCmd('wget', matricesZipUrl, '-O', matricesZipFile)
			import zipfile
			zipObj = zipfile.ZipFile(matricesZipFile, 'r')
			zipObj.extractall(matricesDir)
			zipObj.close()
		return f'{os.environ["HOME"]}/{matricesDir}/matrices'
	return node.runPy(_getMatricesZip, (), utils.runCmd)


@pytest.fixture(scope='session')
def hipccRepo(report, node, manifest):
	repoDir = node.syncGitRepo(manifest['llvm-project']['remote'],
		manifest['llvm-project']['revision'],
	)
	assert repoDir
	ret, out = node.runCmd('git', 'log', '-n', '1', '--pretty=format:"%h%d"', cwd=repoDir)
	report.addFacts(LLVM_COMMIT=out.strip())
	return repoDir


@pytest.fixture(scope='session')
def hipcc(node, hipccRepo):
	buildDir = f'{hipccRepo}/amd/hipcc/build'
	node.runCmd('mkdir', '-p', buildDir, verbose=False)
	ret, out = node.runCmd('cmake', '..', cwd=buildDir)
	assert ret == 0, 'Failed to build hipcc on nvidia platform'
	ret, out = node.runCmd('make', '-j', str(node.getCpuCount()), cwd=buildDir)
	assert ret == 0, 'Failed to compile hipcc on nvidia platform'
	return buildDir


@pytest.fixture(scope='session')
def clrRepo(report, node, manifest):
	repoDir = node.syncGitRepo(manifest['clr']['remote'],
		manifest['clr']['revision'],
	)
	assert repoDir
	ret, out = node.runCmd('git', 'log', '-n', '1', '--pretty=format:"%h%d"', cwd=repoDir)
	report.addFacts(CLR_COMMIT=out.strip())
	return repoDir


@pytest.fixture(scope='session')
def hipRepo(report, node, manifest):
	repoDir = node.syncGitRepo(manifest['hip']['remote'],
		manifest['hip']['revision'],
	)
	assert repoDir
	ret, out = node.runCmd('git', 'log', '-n', '1', '--pretty=format:"%h%d"', cwd=repoDir)
	report.addFacts(HIP_COMMIT=out.strip())
	return repoDir


@pytest.fixture(scope='session')
def hipotherRepo(report, node, manifest):
	repoDir = node.syncGitRepo(manifest['hipother']['remote'],
		manifest['hipother']['revision'],
	)
	assert repoDir
	ret, out = node.runCmd('git', 'log', '-n', '1', '--pretty=format:"%h%d"', cwd=repoDir)
	report.addFacts(HIPOTHER_COMMIT=out.strip())
	return repoDir


@pytest.fixture(scope='session')
def hipNvidia(node, cmake, clrRepo, hipRepo, hipotherRepo, hipcc):
	buildDir = f'{clrRepo}/build'
	installDir = 'install'
	node.runCmd('mkdir', '-p', buildDir, verbose=False)
	ret, out = node.runCmd('cmake', '..',
		'-DHIP_PLATFORM=nvidia',
		'-DHIP_CATCH_TEST=0',
		'-DCLR_BUILD_HIP=ON',
		'-DCLR_BUILD_OCL=OFF',
		f'-DHIP_COMMON_DIR={node.getHomeDir()}/{hipRepo}',
		f'-DHIPCC_BIN_DIR={node.getHomeDir()}/{hipcc}',
		f'-DCMAKE_INSTALL_PREFIX={installDir}',
		f'-DHIPNV_DIR={node.getHomeDir()}/{hipotherRepo}/hipnv',
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to build hip on nvidia platform'
	ret, out = node.runCmd('make', '-j', str(node.getCpuCount()), cwd=buildDir)
	assert ret == 0, 'Failed to compile hip on nvidia platform'
	ret, out = node.runCmd('make', 'install', cwd=buildDir)
	assert ret == 0, 'Failed to install hip on nvidia platform'
	return f'{buildDir}/{installDir}'


@pytest.fixture(scope='session')
def hiptestsRepo(report, node, manifest):
	repoDir = node.syncGitRepo(manifest['hip-tests']['remote'],
		manifest['hip-tests']['revision'],
	)
	assert repoDir
	ret, out = node.runCmd('git', 'log', '-n', '1', '--pretty=format:"%h%d"', cwd=repoDir)
	report.addFacts(HIP_TESTS_COMMIT=out.strip())
	return repoDir


@pytest.fixture(scope='session')
def hipNvidiaTestDir(node, cmake, hipNvidia, hiptestsRepo):
	buildDir = f'{hiptestsRepo}/build'
	node.runCmd('mkdir', '-p', buildDir, verbose=False)
	ret, out = node.runCmd('cmake', '../catch',
		'-DHIP_PLATFORM=nvidia',
		f'-DHIP_PATH={node.getHomeDir()}/{hipNvidia}',
		env={
			'HIP_PLATFORM': 'nvidia',
		},
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to build hip-tests on nvidia platform'
	ret, out = node.runCmd('make', '-j', str(node.getCpuCount()), 'build_tests',
		cwd=buildDir,
	)
	assert ret == 0, 'Failed to compile hip-tests on nvidia platform'
	return buildDir


### refs ###
# hip-tests: https://gerrit-git.amd.com/plugins/gitiles/hip/+/HEAD/docs/install/build.rst
