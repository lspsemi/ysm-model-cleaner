project(xchacha20)
add_library(xchacha20 STATIC src/xchacha20.cc)
target_include_directories(xchacha20 PUBLIC 
    src
)