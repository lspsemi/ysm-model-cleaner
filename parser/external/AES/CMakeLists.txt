cmake_minimum_required(VERSION 3.12...3.31)

project(AES CXX)

set(SOURCE_FILES ${CMAKE_CURRENT_SOURCE_DIR}/src/AES.cpp)
set(INCLUDE_DIR ${CMAKE_CURRENT_SOURCE_DIR}/src)

add_library(${PROJECT_NAME} ${SOURCE_FILES})
target_compile_features(${PROJECT_NAME} PUBLIC cxx_std_11)
target_include_directories(${PROJECT_NAME} PUBLIC ${INCLUDE_DIR})
