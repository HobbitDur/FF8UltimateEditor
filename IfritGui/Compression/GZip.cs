using System.IO;
using System.IO.Compression;

namespace Ifrit.Compression
{
    static class GZip
    {
        public static byte[] Compress(byte[] uncompressedBuffer)
        {
            using (MemoryStream ms = new MemoryStream())
            {
                using(GZipStream gzip = new GZipStream(ms, CompressionMode.Compress))
                {
                    gzip.Write(uncompressedBuffer, 0, uncompressedBuffer.Length);
                    gzip.Flush(); gzip.Close();
                }
                byte[] compressedBuffer = ms.ToArray();
                return compressedBuffer;
            }
        }

        public static byte[] Decompress(byte[] compressedBuffer)
        {
            using(GZipStream gzip = new GZipStream(new MemoryStream(compressedBuffer), CompressionMode.Decompress))
            {
                byte[] uncompressedBuffer = ReadAllBytes(gzip);
                return uncompressedBuffer;
            }
        }

        private static byte[] ReadAllBytes(Stream stream)
        {
            byte[] buffer = new byte[4096];
            using (MemoryStream ms = new MemoryStream())
            {
                int bytesRead = 0;
                do
                {
                    bytesRead = stream.Read(buffer, 0, buffer.Length);
                    if (bytesRead > 0)
                    {
                        ms.Write(buffer, 0, bytesRead);
                    }
                } while (bytesRead > 0);

                return ms.ToArray();
            }
        }
    }
}