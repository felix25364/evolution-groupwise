cmake_minimum_required(VERSION 3.16)
project(thunderbird-groupwise VERSION 0.1.0 LANGUAGES C)
include(GNUInstallDirs)
find_package(PkgConfig REQUIRED)
pkg_check_modules(GIO REQUIRED IMPORTED_TARGET gio-2.0>=2.76)
pkg_check_modules(SOUP REQUIRED IMPORTED_TARGET libsoup-3.0>=3.4)
pkg_check_modules(LIBXML REQUIRED IMPORTED_TARGET libxml-2.0)
pkg_check_modules(JSON REQUIRED IMPORTED_TARGET json-glib-1.0)
set(GW_PRIVLIBDIR "${CMAKE_INSTALL_FULL_LIBDIR}/thunderbird-groupwise")
add_compile_definitions(GETTEXT_PACKAGE="evolution-groupwise")
add_subdirectory(../src/libegroupwise core)
add_executable(groupwise-host native/groupwise-host.c)
target_link_libraries(groupwise-host PRIVATE egroupwise PkgConfig::JSON)
target_compile_options(groupwise-host PRIVATE -Wall -Wextra -Werror -Wno-unused-parameter)
set_target_properties(groupwise-host PROPERTIES INSTALL_RPATH "${GW_PRIVLIBDIR}")
install(TARGETS groupwise-host RUNTIME DESTINATION ${CMAKE_INSTALL_BINDIR})
find_package(Python3 REQUIRED COMPONENTS Interpreter)
enable_testing()
add_test(NAME native-framing COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_host.py $<TARGET_FILE:groupwise-host>)
add_test(NAME native-soap COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/../tests/mock/run-with-mock.py ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_soap.py $<TARGET_FILE:groupwise-host>)
add_custom_target(xpi ALL COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/packaging/linux/package-xpi.py ${CMAKE_CURRENT_SOURCE_DIR}/extension ${CMAKE_CURRENT_BINARY_DIR}/groupwise.xpi)
find_program(NODE_EXECUTABLE NAMES node nodejs)
if(NODE_EXECUTABLE)
  add_test(NAME extension-transport COMMAND ${NODE_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_transport.js)
endif()
add_test(NAME linux-packaging COMMAND ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_packaging.py)
option(GROUPWISE_RUNTIME_TESTS "Run isolated Thunderbird/Xvfb integration tests" OFF)
if(GROUPWISE_RUNTIME_TESTS)
  find_program(THUNDERBIRD_EXECUTABLE thunderbird REQUIRED)
  find_program(XVFB_RUN_EXECUTABLE xvfb-run REQUIRED)
  add_test(NAME thunderbird-runtime COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/../tests/mock/run-with-mock.py
    ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runtime.py
    --xpi ${CMAKE_CURRENT_BINARY_DIR}/groupwise.xpi
    --host $<TARGET_FILE:groupwise-host> --thunderbird ${THUNDERBIRD_EXECUTABLE})
  add_test(NAME thunderbird-html-runtime COMMAND ${Python3_EXECUTABLE}
    ${CMAKE_CURRENT_SOURCE_DIR}/tests/run-runtime-mock.py --html
    ${Python3_EXECUTABLE} ${CMAKE_CURRENT_SOURCE_DIR}/tests/test_runtime.py
    --xpi ${CMAKE_CURRENT_BINARY_DIR}/groupwise.xpi
    --host $<TARGET_FILE:groupwise-host> --thunderbird ${THUNDERBIRD_EXECUTABLE})
  set_tests_properties(thunderbird-runtime thunderbird-html-runtime PROPERTIES TIMEOUT 180 RUN_SERIAL TRUE)
endif()
