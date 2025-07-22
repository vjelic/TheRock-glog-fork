therock_subproject_fetch(therock-fftw-sources
  CMAKE_PROJECT
  # Originally mirrored from: https://fftw.org/fftw-3.3.10.tar.gz
  URL https://fftw.org/fftw-3.3.10.tar.gz
  URL_HASH SHA256=56C932549852CDDCFAFDAB3820B0200C7742675BE92179E59E6215B340E26467
)

therock_cmake_subproject_declare(therock-fftw
  BACKGROUND_BUILD
  EXCLUDE_FROM_ALL
  NO_MERGE_COMPILE_COMMANDS
  OUTPUT_ON_FAILURE
  EXTERNAL_SOURCE_DIR "${CMAKE_CURRENT_BINARY_DIR}/source"
)
therock_cmake_subproject_provide_package(
  therock-fftw fftw lib/cmake/fftw)
therock_cmake_subproject_activate(therock-fftw)

add_dependencies(therock-third-party therock-fftw)
