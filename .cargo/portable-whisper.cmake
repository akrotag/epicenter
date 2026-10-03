# whisper-rs-sys 0.11.1 enables -march=native by default. Release artifacts must
# run on the recipient's CPU, including during Vulkan's static initialization.
# Scope this hook to whisper.cpp/GGML; other CMake dependencies are untouched.
if(CMAKE_SYSTEM_NAME STREQUAL "Linux" AND
   CMAKE_PROJECT_NAME MATCHES "^(whisper\\.cpp|ggml)$")
    set(GGML_NATIVE OFF CACHE BOOL "Portable Linux release" FORCE)

    if(WHISPER_CPU_ONLY)
        set(GGML_VULKAN OFF CACHE BOOL "Local CPU-only transcription" FORCE)
    endif()

    if(CMAKE_SYSTEM_PROCESSOR MATCHES "^(x86_64|AMD64|amd64)$")
        # GGML_NATIVE=OFF alone enables AVX/AVX2/FMA/F16C in this GGML version.
        # Use the x86-64 baseline; GPU backends remain available.
        foreach(feature AVX AVX2 AVX512 AVX512_VBMI AVX512_VNNI AVX512_BF16
                        FMA F16C AMX_TILE AMX_INT8 AMX_BF16)
            set(GGML_${feature} OFF CACHE BOOL "Portable x86-64 release" FORCE)
        endforeach()

        # Explicit local opt-in for CPUs verified to support these instructions.
        # Never inherit AVX-512 or AMX from the build host.
        if(WHISPER_CPU_AVX2)
            foreach(feature AVX AVX2 FMA F16C)
                set(GGML_${feature} ON CACHE BOOL "Verified local AVX2 CPU" FORCE)
            endforeach()
        endif()
    endif()
endif()
