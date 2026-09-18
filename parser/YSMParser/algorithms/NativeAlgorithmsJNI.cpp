#include <jni.h>
#include <cstdint>
#include <cstring>
#include <exception>
#include <memory>
#include <random>
#include <mutex>
#include <unordered_map>
#include <vector>
#include <city.h>
#include <zstd.h>
#include <xchacha20.h>
#include "CryptoAlgorithms.hpp"

// ─── CityHash ────────────────────────────────────────────────────────────────

extern "C" {

JNIEXPORT jlong JNICALL
Java_com_ysm_parser_YSMNative_cityHash64(JNIEnv* env, jclass, jbyteArray data) {
    if (data == nullptr) return 0;
    jbyte* ptr = env->GetByteArrayElements(data, nullptr);
    jsize len = env->GetArrayLength(data);
    uint64_t result = CityHash64(reinterpret_cast<const char*>(ptr), static_cast<size_t>(len));
    env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);
    return static_cast<jlong>(result);
}

JNIEXPORT jlong JNICALL
Java_com_ysm_parser_YSMNative_cityHash64WithSeed(JNIEnv* env, jclass, jbyteArray data, jlong seed) {
    if (data == nullptr) return 0;
    jbyte* ptr = env->GetByteArrayElements(data, nullptr);
    jsize len = env->GetArrayLength(data);
    uint64_t result = CityHash64WithSeed(
        reinterpret_cast<const char*>(ptr),
        static_cast<size_t>(len),
        static_cast<uint64_t>(seed));
    env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);
    return static_cast<jlong>(result);
}

JNIEXPORT jlongArray JNICALL
Java_com_ysm_parser_YSMNative_cityHash128(JNIEnv* env, jclass, jbyteArray data) {
    if (data == nullptr) return nullptr;
    jbyte* ptr = env->GetByteArrayElements(data, nullptr);
    jsize len = env->GetArrayLength(data);
    uint128 result = CityHash128(reinterpret_cast<const char*>(ptr), static_cast<size_t>(len));
    env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);

    jlongArray out = env->NewLongArray(2);
    jlong buf[2] = {
        static_cast<jlong>(Uint128Low64(result)),
        static_cast<jlong>(Uint128High64(result))
    };
    env->SetLongArrayRegion(out, 0, 2, buf);
    return out;
}

JNIEXPORT jlongArray JNICALL
Java_com_ysm_parser_YSMNative_cityHash128WithSeed(JNIEnv* env, jclass, jbyteArray data, jlong seedLow, jlong seedHigh) {
    if (data == nullptr) return nullptr;
    jbyte* ptr = env->GetByteArrayElements(data, nullptr);
    jsize len = env->GetArrayLength(data);
    uint128 seed = {static_cast<uint64_t>(seedLow), static_cast<uint64_t>(seedHigh)};
    uint128 result = CityHash128WithSeed(reinterpret_cast<const char*>(ptr), static_cast<size_t>(len), seed);
    env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);

    jlongArray out = env->NewLongArray(2);
    jlong buf[2] = {
        static_cast<jlong>(Uint128Low64(result)),
        static_cast<jlong>(Uint128High64(result))
    };
    env->SetLongArrayRegion(out, 0, 2, buf);
    return out;
}

// ─── Zstd ────────────────────────────────────────────────────────────────────

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_zstdDecompress(JNIEnv* env, jclass, jbyteArray data) {
    if (data == nullptr) return nullptr;
    jbyte* ptr = env->GetByteArrayElements(data, nullptr);
    jsize len = env->GetArrayLength(data);

    ZSTD_DCtx* dctx = ZSTD_createDCtx();
    if (dctx == nullptr) {
        env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Failed to create ZSTD decompression context");
        return nullptr;
    }

    ZSTD_inBuffer input = {ptr, static_cast<size_t>(len), 0};
    size_t const outBuffSize = ZSTD_DStreamOutSize();
    std::vector<uint8_t> outBuff(outBuffSize);
    std::vector<uint8_t> result;

    while (input.pos < input.size) {
        ZSTD_outBuffer output = {outBuff.data(), outBuff.size(), 0};
        size_t const ret = ZSTD_decompressStream(dctx, &output, &input);
        if (ZSTD_isError(ret)) {
            ZSTD_freeDCtx(dctx);
            env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);
            jclass exClass = env->FindClass("java/lang/RuntimeException");
            env->ThrowNew(exClass, ZSTD_getErrorName(ret));
            return nullptr;
        }
        result.insert(result.end(), outBuff.begin(), outBuff.begin() + output.pos);
    }

    ZSTD_freeDCtx(dctx);
    env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);

    jbyteArray out = env->NewByteArray(static_cast<jsize>(result.size()));
    env->SetByteArrayRegion(out, 0, static_cast<jsize>(result.size()),
                            reinterpret_cast<const jbyte*>(result.data()));
    return out;
}

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_zstdCompress(JNIEnv* env, jclass, jbyteArray data, jint level) {
    if (data == nullptr) return nullptr;
    jbyte* ptr = env->GetByteArrayElements(data, nullptr);
    jsize len = env->GetArrayLength(data);

    size_t const dstBound = ZSTD_compressBound(static_cast<size_t>(len));
    std::vector<uint8_t> dst(dstBound);

    size_t const ret = ZSTD_compress(dst.data(), dst.size(), ptr, static_cast<size_t>(len), static_cast<int>(level));
    env->ReleaseByteArrayElements(data, ptr, JNI_ABORT);

    if (ZSTD_isError(ret)) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, ZSTD_getErrorName(ret));
        return nullptr;
    }

    jbyteArray out = env->NewByteArray(static_cast<jsize>(ret));
    env->SetByteArrayRegion(out, 0, static_cast<jsize>(ret), reinterpret_cast<const jbyte*>(dst.data()));
    return out;
}

// ─── XChaCha20 ───────────────────────────────────────────────────────────────

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_xchacha20Encrypt(JNIEnv* env, jclass,
        jbyteArray data, jbyteArray key, jbyteArray iv, jint rounds) {
    if (data == nullptr || key == nullptr || iv == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "data, key, and iv must not be null");
        return nullptr;
    }
    if (env->GetArrayLength(key) != 32 || env->GetArrayLength(iv) != 24) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Key must be 32 bytes and IV must be 24 bytes");
        return nullptr;
    }

    jbyte* dataPtr = env->GetByteArrayElements(data, nullptr);
    jbyte* keyPtr  = env->GetByteArrayElements(key,  nullptr);
    jbyte* ivPtr   = env->GetByteArrayElements(iv,   nullptr);
    jsize dataLen  = env->GetArrayLength(data);

    XChaCha_ctx ctx;
    ctx.rounds = static_cast<uint32_t>(rounds);
    xchacha_keysetup(&ctx, reinterpret_cast<const uint8_t*>(keyPtr), reinterpret_cast<const uint8_t*>(ivPtr));

    std::vector<uint8_t> outBuf(static_cast<size_t>(dataLen));
    xchacha_encrypt_bytes(&ctx,
        reinterpret_cast<const uint8_t*>(dataPtr),
        outBuf.data(),
        static_cast<uint32_t>(dataLen));

    env->ReleaseByteArrayElements(data, dataPtr, JNI_ABORT);
    env->ReleaseByteArrayElements(key,  keyPtr,  JNI_ABORT);
    env->ReleaseByteArrayElements(iv,   ivPtr,   JNI_ABORT);

    jbyteArray out = env->NewByteArray(dataLen);
    env->SetByteArrayRegion(out, 0, dataLen, reinterpret_cast<const jbyte*>(outBuf.data()));
    return out;
}

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_xchacha20Decrypt(JNIEnv* env, jclass,
        jbyteArray data, jbyteArray key, jbyteArray iv, jint rounds) {
    // XChaCha20 is a stream cipher — encrypt and decrypt are the same operation
    return Java_com_ysm_parser_YSMNative_xchacha20Encrypt(env, nullptr, data, key, iv, rounds);
}

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_modifiedChaChaDecrypt(JNIEnv* env, jclass,
        jbyteArray data, jbyteArray key, jbyteArray iv, jlong seed) {
    if (data == nullptr || key == nullptr || iv == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "data, key, and iv must not be null");
        return nullptr;
    }
    if (env->GetArrayLength(key) != 32 || env->GetArrayLength(iv) != 24) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Key must be 32 bytes and IV must be 24 bytes");
        return nullptr;
    }

    try {
        const jsize dataLen = env->GetArrayLength(data);
        std::vector<uint8_t> input(static_cast<size_t>(dataLen));
        std::vector<uint8_t> keyBytes(32);
        std::vector<uint8_t> ivBytes(24);

        if (dataLen > 0) {
            env->GetByteArrayRegion(data, 0, dataLen, reinterpret_cast<jbyte*>(input.data()));
            if (env->ExceptionCheck()) return nullptr;
        }
        env->GetByteArrayRegion(key, 0, 32, reinterpret_cast<jbyte*>(keyBytes.data()));
        if (env->ExceptionCheck()) return nullptr;
        env->GetByteArrayRegion(iv, 0, 24, reinterpret_cast<jbyte*>(ivBytes.data()));
        if (env->ExceptionCheck()) return nullptr;

        std::vector<uint8_t> result = CryptoUtils::ModifiedChaChaDecrypt(
            input,
            keyBytes.data(),
            ivBytes.data(),
            static_cast<uint64_t>(seed));

        jbyteArray out = env->NewByteArray(static_cast<jsize>(result.size()));
        if (out == nullptr) return nullptr;
        if (!result.empty()) {
            env->SetByteArrayRegion(out, 0, static_cast<jsize>(result.size()),
                                    reinterpret_cast<const jbyte*>(result.data()));
        }
        return out;
    } catch (const std::exception& e) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return nullptr;
    } catch (...) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error during ModifiedChaCha decrypt");
        return nullptr;
    }
}


JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_modifiedChaChaEncrypt(JNIEnv* env, jclass,
    jbyteArray data, jbyteArray key, jbyteArray iv, jlong seed) {
    if (data == nullptr || key == nullptr || iv == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "data, key, and iv must not be null");
        return nullptr;
    }
    if (env->GetArrayLength(key) != 32 || env->GetArrayLength(iv) != 24) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Key must be 32 bytes and IV must be 24 bytes");
        return nullptr;
    }

    try {
        const jsize dataLen = env->GetArrayLength(data);
        std::vector<uint8_t> input(static_cast<size_t>(dataLen));
        std::vector<uint8_t> keyBytes(32);
        std::vector<uint8_t> ivBytes(24);

        if (dataLen > 0) {
            env->GetByteArrayRegion(data, 0, dataLen, reinterpret_cast<jbyte*>(input.data()));
            if (env->ExceptionCheck()) return nullptr;
        }
        env->GetByteArrayRegion(key, 0, 32, reinterpret_cast<jbyte*>(keyBytes.data()));
        if (env->ExceptionCheck()) return nullptr;
        env->GetByteArrayRegion(iv, 0, 24, reinterpret_cast<jbyte*>(ivBytes.data()));
        if (env->ExceptionCheck()) return nullptr;

        std::vector<uint8_t> result = CryptoUtils::ModifiedChaChaEncrypt(
            input,
            keyBytes.data(),
            ivBytes.data(),
            static_cast<uint64_t>(seed));

        jbyteArray out = env->NewByteArray(static_cast<jsize>(result.size()));
        if (out == nullptr) return nullptr;
        if (!result.empty()) {
            env->SetByteArrayRegion(out, 0, static_cast<jsize>(result.size()),
                reinterpret_cast<const jbyte*>(result.data()));
        }
        return out;
    }
    catch (const std::exception& e) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return nullptr;
    }
    catch (...) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error during ModifiedChaCha encrypt");
        return nullptr;
    }
}

// ─── MT19937 (stateful) ──────────────────────────────────────────────────────

namespace {
    std::mutex g_mtMutex;
    uint64_t g_mtNextHandle = 1;
    std::unordered_map<uint64_t, std::unique_ptr<std::mt19937_64>> g_mtStates;

    std::mt19937_64* getMTEngine(uint64_t handle) {
        auto it = g_mtStates.find(handle);
        return (it != g_mtStates.end()) ? it->second.get() : nullptr;
    }
}

JNIEXPORT jlong JNICALL
Java_com_ysm_parser_YSMNative_mt19937Create(JNIEnv*, jclass, jlong seed) {
    auto engine = std::make_unique<std::mt19937_64>(static_cast<uint64_t>(seed));
    std::lock_guard<std::mutex> lock(g_mtMutex);
    uint64_t handle = g_mtNextHandle++;
    g_mtStates[handle] = std::move(engine);
    return static_cast<jlong>(handle);
}

JNIEXPORT jlong JNICALL
Java_com_ysm_parser_YSMNative_mt19937Next(JNIEnv* env, jclass, jlong handle) {
    std::lock_guard<std::mutex> lock(g_mtMutex);
    auto* engine = getMTEngine(static_cast<uint64_t>(handle));
    if (engine == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Invalid or destroyed MT19937 handle");
        return 0;
    }
    return static_cast<jlong>((*engine)());
}

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_mt19937GenerateBytes(JNIEnv* env, jclass, jlong handle, jint count) {
    if (count < 0) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Byte count must be non-negative");
        return nullptr;
    }
    std::lock_guard<std::mutex> lock(g_mtMutex);
    auto* engine = getMTEngine(static_cast<uint64_t>(handle));
    if (engine == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Invalid or destroyed MT19937 handle");
        return nullptr;
    }

    jbyteArray out = env->NewByteArray(count);
    if (count == 0) return out;

    jbyte* outPtr = env->GetByteArrayElements(out, nullptr);
    size_t written = 0;
    while (written < static_cast<size_t>(count)) {
        uint64_t rnd = (*engine)();
        for (int j = 0; j < 8 && written < static_cast<size_t>(count); ++j) {
            outPtr[written] = static_cast<jbyte>((rnd >> (j * 8)) & 0xFF);
            ++written;
        }
    }
    env->ReleaseByteArrayElements(out, outPtr, 0);
    return out;
}

JNIEXPORT void JNICALL
Java_com_ysm_parser_YSMNative_mt19937Destroy(JNIEnv*, jclass, jlong handle) {
    std::lock_guard<std::mutex> lock(g_mtMutex);
    g_mtStates.erase(static_cast<uint64_t>(handle));
}


JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_ysmZstdDecompress(JNIEnv* env, jclass, jbyteArray data) {
    if (data == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Input data cannot be null");
        return nullptr;
    }

    try {
        jsize len = env->GetArrayLength(data);
        std::vector<uint8_t> input(static_cast<size_t>(len));

        if (len > 0) {
            env->GetByteArrayRegion(data, 0, len, reinterpret_cast<jbyte*>(input.data()));
            if (env->ExceptionCheck()) return nullptr; // 内存溢出或其他异常直接返回
        }

        // 调用 C++ 核心解码（附带 wash）
        std::vector<uint8_t> result = CryptoUtils::DecompressZstd(input);

        jbyteArray out = env->NewByteArray(static_cast<jsize>(result.size()));
        if (out == nullptr) return nullptr;
        if (!result.empty()) {
            env->SetByteArrayRegion(out, 0, static_cast<jsize>(result.size()),
                reinterpret_cast<const jbyte*>(result.data()));
        }
        return out;

    }
    catch (const std::exception& e) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return nullptr;
    }
    catch (...) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error during YSM ZSTD decompression");
        return nullptr;
    }
}

JNIEXPORT jbyteArray JNICALL
Java_com_ysm_parser_YSMNative_ysmZstdCompress(JNIEnv* env, jclass, jbyteArray data, jint level) {
    if (data == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Input data cannot be null");
        return nullptr;
    }

    try {
        jsize len = env->GetArrayLength(data);
        std::vector<uint8_t> input(static_cast<size_t>(len));

        if (len > 0) {
            env->GetByteArrayRegion(data, 0, len, reinterpret_cast<jbyte*>(input.data()));
            if (env->ExceptionCheck()) return nullptr;
        }

        // 调用 C++ 核心编码（附带 obfuscate）
        std::vector<uint8_t> result = CryptoUtils::CompressZstd(input, static_cast<int>(level));

        jbyteArray out = env->NewByteArray(static_cast<jsize>(result.size()));
        if (out == nullptr) return nullptr;
        if (!result.empty()) {
            env->SetByteArrayRegion(out, 0, static_cast<jsize>(result.size()),
                reinterpret_cast<const jbyte*>(result.data()));
        }
        return out;

    }
    catch (const std::exception& e) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return nullptr;
    }
    catch (...) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error during YSM ZSTD compression");
        return nullptr;
    }
}
} // extern "C"
