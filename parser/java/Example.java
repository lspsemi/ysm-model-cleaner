import com.ysm.parser.YSMParser;
import com.ysm.parser.YSMNative;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Paths;

/**
 * Usage example for YSMParser JNI library.
 *
 * <p>Build the native library first:
 * <pre>{@code
 *   cmake --preset x64-release -DYSM_TARGET_JNI=ON
 *   cmake --build --preset x64-release
 * }</pre>
 *
 * <p>Then compile and run:
 * <pre>{@code
 *   javac -d out java/Example.java java/com/ysm/parser/YSMParser.java java/com/ysm/parser/YSMNative.java
 *   java -Djava.library.path=out/install/x64-release -cp out Example input.ysm ./output
 * }</pre>
 */
public class Example {

    public static void main(String[] args) throws Exception {
        if (args.length < 2) {
            printUsage();
            return;
        }

        String mode = args[0];

        switch (mode) {
            case "parse" -> parseExample(args);
            case "version" -> versionExample(args);
            case "native" -> nativeExample(args);
            default -> printUsage();
        }
    }

    // ── Parse a .ysm file ──────────────────────────────────────────────────

    static void parseExample(String[] args) {
        if (args.length < 3) {
            System.err.println("Usage: Example parse <ysm-file> <output-dir>");
            return;
        }
        String ysmFile = args[1];
        String outputDir = args[2];

        System.out.println("Parsing: " + ysmFile);
        System.out.println("Output:  " + outputDir);

        boolean ok = YSMParser.parse(ysmFile, outputDir);
        System.out.println(ok ? "Done." : "Failed.");
    }

    // ── Read version without full parsing ────────────────────────────────

    static void versionExample(String[] args) {
        if (args.length < 2) {
            System.err.println("Usage: Example version <ysm-file>");
            return;
        }
        int version = YSMParser.getVersion(args[1]);
        System.out.println("YSGP version: " + version);
    }

    // ── Low-level algorithm demo ─────────────────────────────────────────

    static void nativeExample(String[] args) throws IOException {
        System.out.println("=== CityHash ===");
        byte[] data = "Hello, YSM!".getBytes();
        long h64 = YSMNative.cityHash64(data);
        long h64s = YSMNative.cityHash64WithSeed(data, 0x9E5599DB80C67C29L);
        System.out.printf("cityHash64:           %016X%n", h64);
        System.out.printf("cityHash64WithSeed:   %016X%n", h64s);

        long[] h128 = YSMNative.cityHash128(data);
        System.out.printf("cityHash128:          %016X %016X%n", h128[0], h128[1]);

        System.out.println("\n=== Zstd ===");
        byte[] compressed = YSMNative.zstdCompress(data, 3);
        System.out.printf("Original:   %d bytes%n", data.length);
        System.out.printf("Compressed: %d bytes%n", compressed.length);
        byte[] decompressed = YSMNative.zstdDecompress(compressed);
        System.out.println("Roundtrip:  " + new String(decompressed));

        System.out.println("\n=== XChaCha20 ===");
        byte[] key = new byte[32];
        byte[] iv = new byte[24];
        for (int i = 0; i < 32; i++) key[i] = (byte) (i + 1);
        for (int i = 0; i < 24; i++) iv[i] = (byte) ((i * 7 + 3) & 0xFF);
        byte[] encrypted = YSMNative.xchacha20Encrypt(data, key, iv, 20);
        byte[] decrypted = YSMNative.xchacha20Decrypt(encrypted, key, iv, 20);
        System.out.println("Plaintext:  " + new String(data));
        System.out.println("Decrypted:  " + new String(decrypted));

        System.out.println("\n=== MT19937 ===");
        long handle = YSMNative.mt19937Create(0xD017CBBA7B5D3581L);
        System.out.printf("First u64:  %016X%n", YSMNative.mt19937Next(handle));
        byte[] rndBytes = YSMNative.mt19937GenerateBytes(handle, 16);
        System.out.print("16 bytes:   ");
        for (byte b : rndBytes) System.out.printf("%02X ", b & 0xFF);
        System.out.println();
        YSMNative.mt19937Destroy(handle);
        System.out.println("(handle destroyed)");
    }

    static void printUsage() {
        System.out.println("""
            YSMParser JNI Example
            ─────────────────────
              Example parse   <ysm-file> <output-dir>
              Example version <ysm-file>
              Example native
            """);
    }
}
