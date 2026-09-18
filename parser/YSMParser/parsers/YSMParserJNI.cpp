#include <jni.h>
#include <string>
#include <memory>
#include "YSMParser.hpp"
#include "../platform/PlatformCompat.hpp"

extern "C" {

JNIEXPORT jboolean JNICALL
Java_com_ysm_parser_YSMParser_parse(JNIEnv* env, jclass clazz, jstring ysmFilePath, jstring outputDir) {
    if (ysmFilePath == nullptr || outputDir == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Input path and output directory must not be null");
        return JNI_FALSE;
    }

    const char* inputChars = env->GetStringUTFChars(ysmFilePath, nullptr);
    const char* outputChars = env->GetStringUTFChars(outputDir, nullptr);

    if (inputChars == nullptr || outputChars == nullptr) {
        if (inputChars) env->ReleaseStringUTFChars(ysmFilePath, inputChars);
        if (outputChars) env->ReleaseStringUTFChars(outputDir, outputChars);
        return JNI_FALSE;
    }

    std::string inputPath(inputChars);
    std::string outputPath(outputChars);

    env->ReleaseStringUTFChars(ysmFilePath, inputChars);
    env->ReleaseStringUTFChars(outputDir, outputChars);

    try {
        auto parser = YSMParserFactory::Create(inputPath);
        parser->parse();
        parser->saveToDirectory(outputPath);
        return JNI_TRUE;
    } catch (const std::exception& e) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return JNI_FALSE;
    } catch (...) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error during YSM parsing");
        return JNI_FALSE;
    }
}

JNIEXPORT jboolean JNICALL
Java_com_ysm_parser_YSMParser_parseBytes(JNIEnv* env, jclass clazz, jbyteArray ysmData, jstring outputDir) {
    if (ysmData == nullptr || outputDir == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Data and output directory must not be null");
        return JNI_FALSE;
    }

    const char* outputChars = env->GetStringUTFChars(outputDir, nullptr);
    if (outputChars == nullptr) return JNI_FALSE;
    std::string outputPath(outputChars);
    env->ReleaseStringUTFChars(outputDir, outputChars);

    jsize dataLen = env->GetArrayLength(ysmData);
    if (dataLen == 0) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Data must not be empty");
        return JNI_FALSE;
    }

    jbyte* dataPtr = env->GetByteArrayElements(ysmData, nullptr);
    if (dataPtr == nullptr) return JNI_FALSE;

    try {
        auto parser = YSMParserFactory::Create(reinterpret_cast<const char*>(dataPtr), static_cast<size_t>(dataLen));
        parser->parse();
        parser->saveToDirectory(outputPath);
        env->ReleaseByteArrayElements(ysmData, dataPtr, JNI_ABORT);
        return JNI_TRUE;
    } catch (const std::exception& e) {
        env->ReleaseByteArrayElements(ysmData, dataPtr, JNI_ABORT);
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return JNI_FALSE;
    } catch (...) {
        env->ReleaseByteArrayElements(ysmData, dataPtr, JNI_ABORT);
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error during YSM parsing");
        return JNI_FALSE;
    }
}

JNIEXPORT jint JNICALL
Java_com_ysm_parser_YSMParser_getVersion(JNIEnv* env, jclass clazz, jstring ysmFilePath) {
    if (ysmFilePath == nullptr) {
        jclass exClass = env->FindClass("java/lang/IllegalArgumentException");
        env->ThrowNew(exClass, "Input path must not be null");
        return -1;
    }

    const char* inputChars = env->GetStringUTFChars(ysmFilePath, nullptr);
    if (inputChars == nullptr) return -1;

    std::string inputPath(inputChars);
    env->ReleaseStringUTFChars(ysmFilePath, inputChars);

    try {
        auto parser = YSMParserFactory::Create(inputPath);
        return parser->getYSGPVersion();
    } catch (const std::exception& e) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, e.what());
        return -1;
    } catch (...) {
        jclass exClass = env->FindClass("java/lang/RuntimeException");
        env->ThrowNew(exClass, "Unknown native error");
        return -1;
    }
}

} // extern "C"
