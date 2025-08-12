import os
import re
import sys
import time
import pytest

from libs import utils
log = utils.log


class TestSuite:
	def _addResult(self, pytestconfig, request, pipeline, report, count, result, verdict, startTime):
		testName = request.node.name
		# verdict
		verdictStr = ('FAIL', 'PASS')[verdict]
		for mark in request.node.own_markers:
			if mark.name == 'xfail':
				reason = mark.kwargs.get('reason', 'UnknownReason')
				verdictStr = (f'XFAIL [{reason}]', f'XPASS [{reason}]')[verdict]
				break
		# pipeline links
		if pipeline:
			logDir = pytestconfig.getoption('logDir')
			script, cls, name = re.search(r'(\w+).py::(\w+)::(.*)', request.node.nodeid).groups()
			logDir = re.sub(r'\W', '_', f'{logDir}{name}')
			logUrl = f'{pipeline.fullUrl}/testReport/junit/{script}/{cls}/{logDir}/'
			verdictStr = f'<a href="{logUrl}">{verdictStr}</a>'
		# execution time
		execTime = time.strftime('%H:%M:%S', time.gmtime(time.time()-startTime))
		result.addResult(testName, verdictStr, execTime)
		# iteration report
		if count:
			count.total += 1
			if verdict:
				count.pCount += 1
			else:
				count.fCount += 1
			count.addResult(request.node.originalname, count.fCount, count.pCount, count.total)
			count.total == 1 and report.setTitle(f' - {request.node.originalname}')


	def test_rocminfo(self, pytestconfig, request, pipeline, node, rocm, report, count, result):
		startTime = time.time()
		exprList = (
			r'ROCk module.*? is loaded',
			r'Name:\s+gfx',
			r'Vendor Name:\s+AMD',
			r'Device Type:\s+GPU',
			r'L2:\s+.*? KB',
		)
		ret, out = node.runCmd('rocminfo')
		if ret == 127: # retry when bin/rocminfo not exists
			ret, out = node.runCmd('./bin/rocminfo', cwd=rocm)
		verdict = all((bool(ret == 0), *[
			re.search(expr, out) or log(f'Expr Not Match: {expr}') for expr in exprList
		]))
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_clinfo(self, pytestconfig, request, pipeline, node, rocm, report, count, result):
		startTime = time.time()
		exprList = (
			r'Number of devices:\s+\d',
			r'Device Type:\s+.*?GPU',
			r'Board name:\s+AMD',
			r'Max compute units:\s+\d+',
			r'Name:\s+gfx',
			r'Vendor:\s+Advanced Micro Devices, Inc',
			r'Extensions:\s+cl_',
			r'Version:\s+OpenCL',
		)
		ret, out = node.runCmd('./bin/clinfo', cwd=rocm)
		verdict = all((bool(ret == 0), *[
			re.search(expr, out) or log(f'Expr Not Match: {expr}') for expr in exprList
		]))
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rbt(self, pytestconfig, request, pipeline, node, rocm, rbtTestDir, report, count, result):
		startTime = time.time()
		cmd = (('./rocm_bandwidth_test', 'plugin', '-i'), ('./rocm-bandwidth-test', ))['6.4' in rocm]
		ret, out = node.runCmd('pudo', *cmd, cwd=rbtTestDir)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocm_debug_agent(self, pytestconfig, request, pipeline, node, rocm, rdaTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'python3', '../run-test.py', '.',
			cwd=rdaTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_kfd(self, pytestconfig, request, pipeline, node, rocm, kfdTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', './run_kfdtest.sh',
			cwd=kfdTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_amdsmi(self, pytestconfig, request, pipeline, node, rocm, amdsmiTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('source', 'amdsmitst.exclude;',
			'pudo', './amdsmitst',
			'--gtest_filter=-${BLACKLIST_ALL_ASICS}',
			cwd=amdsmiTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rsmi(self, pytestconfig, request, pipeline, node, rocm, smiTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('source', 'rsmitst.exclude;',
			'pudo', './rsmitst',
			'--gtest_output=xml:/home/jenkins/compute-package/test_results.xml',
			'--gtest_filter=-${FILTER[aldebaran]}',
			cwd=smiTestDir,
			env={
				'LD_LIBRARY_PATH': '.:$LD_LIBRARY_PATH',
			},
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_ocl(self, pytestconfig, request, pipeline, node, oclTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', './ocltst',
			'-m', 'liboclruntime.so',
			'-A', 'oclruntime.exclude',
			cwd=oclTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.xfail(reason='SWDEV-488889,SWDEV-488893')
	def test_rocrtst(self, pytestconfig, request, pipeline, node, rocrTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rocrtst64',
			cwd=rocrTestDir,
			env={
				'LD_LIBRARY_PATH': '/opt/rocm/lib/rocrtst/lib:/opt/rocm/lib:$LD_LIBRARY_PATH',
			},
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocgdb(self, pytestconfig, request, pipeline, node, rocm, gdbTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'make', 'check',
			'TESTS="gdb.rocm/*.exp"',
			f'RUNTESTFLAGS="GDB={rocm}/bin/rocgdb"',
			cwd=gdbTestDir,
		)
		verdict = not bool(re.search(r'unexpected failures\s+\d+', out))
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.parametrize(
		argnames=('suite'),
		argvalues=(
			pytest.param('tests-v1/run.sh', marks=pytest.mark.rocprofilerv1),
			pytest.param('tests/runUnitTests', marks=pytest.mark.rocprofilerv2),
			pytest.param('tests/runCoreUnitTests', marks=pytest.mark.rocprofilerv2),
			pytest.param('tests/runFeatureTests', marks=pytest.mark.rocprofilerv2),
			pytest.param('tests/runTracerFeatureTests', marks=pytest.mark.rocprofilerv2),
		),
	)
	def test_rocprofiler(self, pytestconfig, request, pipeline, node, rocm, profilerTestDir, suite, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd(f'./{suite}',
			env={'LD_LIBRARY_PATH': f'{rocm}/lib:$LD_LIBRARY_PATH'},
			cwd=profilerTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocprofilerSdk(self, pytestconfig, request, pipeline, node, rocm, profilerSdkTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--test-dir', 'build',
			'--output-on-failure',
			cwd=profilerSdkTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.xfail(reason='SWDEV-526051')
	def test_hipfort(self, pytestconfig, request, pipeline, node, hipfortTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('make', 'run_all',
			env={'PATH': '/opt/rocm/bin:$PATH'},
			cwd=hipfortTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_aqlprofiler(self, pytestconfig, request, pipeline, node, aqlProfilerTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./run_tests.sh', cwd=aqlProfilerTestDir)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_roctracer(self, pytestconfig, request, pipeline, node, tracerTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', './run_tests.sh', cwd=tracerTestDir)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	#@pytest.mark.xfail(reason='SWDEV-489852')
	def test_hiprocclr(self, pytestconfig, request, pipeline, node, hipTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=hipTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.xfail(reason='SWDEV-541362')
	def test_hipnvidia(self, pytestconfig, request, pipeline, node, hipNvidiaTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=hipNvidiaTestDir,
			env={
				'HIP_PLATFORM': 'nvidia',
			},
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_hipcub(self, pytestconfig, request, pipeline, node, hipcubTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=hipcubTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocprim(self, pytestconfig, request, pipeline, node, rocprimTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=rocprimTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocrand(self, pytestconfig, request, pipeline, node, rocrandTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=rocrandTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocthrust(self, pytestconfig, request, pipeline, node, rocthrustTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=rocthrustTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.xfail(reason='SWDEV-496220')
	def test_migraphx(self, pytestconfig, request, pipeline, node, migraphxTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			'-DONNX_USE_PROTOBUF_SHARED_LIBS=ON',
			env={'LD_LIBRARY_PATH': '/opt/rocm/lib:$LD_LIBRARY_PATH'},
			cwd=migraphxTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_mivisionx(self, pytestconfig, request, pipeline, node, mivisionxTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('pudo', 'ctest',
			'--no-tests=error',
			'--output-on-failure',
			cwd=mivisionxTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_hipblas(self, pytestconfig, request, pipeline, node, hipblasTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./hipblas-test', cwd=hipblasTestDir)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_hipfft(self, pytestconfig, request, pipeline, node, hipfftTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./hipfft-test', cwd=hipfftTestDir)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_hipsolver(self, pytestconfig, request, pipeline, node, hipsolverTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./hipsolver-test',
			'--gtest_filter=*float_complex*-*known_bug*',
			cwd=hipsolverTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocalution(self, pytestconfig, request, pipeline, node, rocalutionTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rocalution-test',
			'--gtest_filter=*backend/parameterized_backend*',
			cwd=rocalutionTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocblas(self, pytestconfig, request, pipeline, node, rocblasTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rocblas-test',
			'--gtest_filter=*quick*:*pre_checkin*-*known_bugs*',
			env={'GTEST_LISTENER': 'PASS_LINE_IN_LOG'},
			cwd=rocblasTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocfft(self, pytestconfig, request, pipeline, node, rocfftTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rocfft-test',
			'--gtest_filter=*pow2_1D/accuracy_test*',
			cwd=rocfftTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocsolver(self, pytestconfig, request, pipeline, node, rocsolverTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rocsolver-test',
			cwd=rocsolverTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_rocsparse(self, pytestconfig, request, pipeline, node, rocsparseMatricesDir, rocsparseTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rocsparse-test',
			'--gtest_filter=*quick*',
			env={'ROCSPARSE_CLIENTS_MATRICES_DIR': rocsparseMatricesDir},
			cwd=rocsparseTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	def test_hipsparse(self, pytestconfig, request, pipeline, node, hipsparseMatricesDir, hipsparseTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./hipsparse-test',
			env={'HIPSPARSE_CLIENTS_MATRICES_DIR': hipsparseMatricesDir},
			cwd=hipsparseTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.xfail(reason='SWDEV-496227')
	def test_rccl(self, pytestconfig, request, pipeline, node, rcclTestDir, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rccl-UnitTests', cwd=rcclTestDir)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


	@pytest.mark.parametrize(
		argnames=('suite'),
		argvalues=(
			'iet',
			'gst',
		),
	)
	def test_rvs(self, pytestconfig, request, pipeline, node, rocm, rvsTestDir, suite, report, count, result):
		startTime = time.time()
		ret, out = node.runCmd('./rvs',
			'-c', f'{rocm}/share/rocm-validation-suite/conf/{suite}_single.conf',
			'-d', '3',
			cwd=rvsTestDir,
		)
		verdict = bool(ret == 0)
		self._addResult(pytestconfig, request, pipeline, report, count, result, verdict, startTime)
		assert verdict


### refs ###
# ctest manual: https://cmake.org/cmake/help/latest/manual/ctest.1.html
