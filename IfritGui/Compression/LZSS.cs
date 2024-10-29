using System;
using System.Collections.Generic;
using System.IO;
namespace Ifrit.Compression
{
    public static class LZSS
    {
        //*************************************************************
        //	LZSS.cs -- A Data Compression Program
        //	(tab = 4 spaces)
        //***************************************************************
        //	Original LZSS.c by Haruhiko Okumura 4/6/1989
        //	Use, distribute, and modify this program freely.
        //	Please send me your improved versions.
        //		PC-VAN		SCIENCE
        //		NIFTY-Serve	PAF01022
        //		CompuServe	74050,1022
        //*************************************************************
        internal const int EOF = -1;
        // counter for reporting progress every 1K bytes  -  code size counter  -  text size counter
        internal static uint textsize = 0; 
        internal static uint codesize = 0;
        internal static uint printcount = 0;
        //ring buffer of size N, with extra F-1 bytes to facilitate string comparison
        internal static byte[] text_buf = new byte[LZSSConsts.NF1];
        internal static int match_position; 
        internal static int match_length;
        //left & right children & -  of longest match. These are set by the InsertNode() procedure.
        internal static int[] lson = new int[LZSSConsts.N + 1];
        internal static int[] rson = new int[LZSSConsts.N + 257];
        //parents -- These constitute binary search trees.
        internal static int[] dad = new int[LZSSConsts.N + 1];

        internal static void InitTree() // initialize trees 
        {
            int i;

            /*     For i = 0 to N - 1, rson[i] and lson[i] will be the right and
             *	   left children of node i.  These nodes need not be initialized.
             *	   Also, dad[i] is the parent of node i.  These are initialized to
             *	   NIL (= N), which stands for 'not used.'
             *	   For i = 0 to 255, rson[N + i + 1] is the root of the tree
             *	   for strings that begin with character i.  These are initialized
             *	   to NIL.  Note there are 256 trees. */

            for (i = LZSSConsts.N + 1; i <= LZSSConsts.N + 256; i++)
                rson[i] = LZSSConsts.N;
            for (i = 0; i < LZSSConsts.N; i++)
                dad[i] = LZSSConsts.N;
        }

        internal static unsafe void InsertNode(int r)
        /*     Inserts string of length F, text_buf[r..r+F-1], into one of the
         *	   trees (text_buf[r]'th tree) and returns the longest-match position
         *	   and length via the global variables match_position and match_length.
         *	   If match_length = F, then removes the old node in favor of the new
         *	   one, because the old one will be deleted sooner.
         *	   Note r plays double role, as tree node and position in buffer. */
        {
            int i;
            int p;
            int cmp = 1;

            fixed (byte* key = &text_buf[r])
            {
                p = LZSSConsts.N + 1 + key[0];
                rson[r] = lson[r] = LZSSConsts.N;
                match_length = 0;
                for (; ; )
                {
                    if (cmp >= 0)
                    {
                        if (rson[p] != LZSSConsts.N)
                            p = rson[p];
                        else
                        {
                            rson[p] = r;
                            dad[r] = p;
                            return;
                        }
                    }
                    else
                    {
                        if (lson[p] != LZSSConsts.N)
                            p = lson[p];
                        else
                        {
                            lson[p] = r;
                            dad[r] = p;
                            return;
                        }
                    }
                    for (i = 1; i < LZSSConsts.F; i++)
                        if ((cmp = key[i] - text_buf[p + i]) != 0)
                            break;
                    if (i > match_length)
                    {
                        match_position = p;
                        if ((match_length = i) >= LZSSConsts.F)
                            break;
                    }
                }
                dad[r] = dad[p];
                lson[r] = lson[p];
                rson[r] = rson[p];
                dad[lson[p]] = r;
                dad[rson[p]] = r;
                if (rson[dad[p]] == p)
                    rson[dad[p]] = r;
                else
                    lson[dad[p]] = r;
                dad[p] = LZSSConsts.N; // remove p 
            }
        }

        internal static void DeleteNode(int p) // deletes node p from tree 
        {
            int q;

            if (dad[p] == LZSSConsts.N) // not in tree 
                return;
            if (rson[p] == LZSSConsts.N)
                q = lson[p];
            else if (lson[p] == LZSSConsts.N)
                q = rson[p];
            else
            {
                q = lson[p];
                if (rson[q] != LZSSConsts.N)
                {
                    do
                    {
                        q = rson[q];
                    } while (rson[q] != LZSSConsts.N);
                    rson[dad[q]] = lson[q];
                    dad[lson[q]] = dad[q];
                    lson[q] = lson[p];
                    dad[lson[p]] = q;
                }
                rson[q] = rson[p];
                dad[rson[p]] = q;
            }
            dad[q] = dad[p];
            if (rson[dad[p]] == p)
                rson[dad[p]] = q;
            else
                lson[dad[p]] = q;
            dad[p] = LZSSConsts.N;
        }

        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will decode until the end of the stream.
        /// </summary>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader) { return Encode(byteReader, 0, 0, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will decode from given position until the end of the stream.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, long position) { return Encode(byteReader, position, 0, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will decode until the end of the stream.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, byte fillByte) { return Encode(byteReader, 0, fillByte, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will decode until the end of the stream or chosen position (end of stream will be prioritized).
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, ulong end) { return Encode(byteReader, 0, 0, end); }
        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will decode from given position until the end of the stream.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, long position, byte fillByte) { return Encode(byteReader, position, fillByte, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Encoding (or compression)) based on a stream. Will decode from given position until chosen position.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, long position, ulong end) { return Encode(byteReader, position, 0, end); }
        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will decode until the chosen position.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, byte fillByte, ulong end) { return Encode(byteReader, 0, fillByte, end); }
        /// <summary>
        /// LZSS Encoding (or compression) based on a stream. Will encode from given position until the end of the stream or chosen position (end of stream will be prioritized).
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the encoding will be forced to end.</param>
        /// <returns>The encoded stream of bytes.</returns>
        public static byte[] Encode(Stream byteReader, long position, byte fillByte, ulong end)
        {
            int i;
            int c;
            int len;
            int r;
            int s;
            int last_match_length;
            int code_buf_ptr;
            byte[] code_buf = new byte[17];
            byte mask;
            List<byte> byteWriter = new List<byte>();
            byteReader.Position = position;

            InitTree(); // initialize trees 
            code_buf[0] = 0; /*code_buf[1..16] saves eight units of code, and
            		code_buf[0] works as eight flags, "1" representing that the unit
            		is an unencoded letter (1 byte), "0" a position-and-length pair
            		(2 bytes).  Thus, eight units require at most 16 bytes of code.*/
            code_buf_ptr = mask = 1;
            s = 0;
            r = LZSSConsts.N - LZSSConsts.F;

            /* Clear the buffer with any character that will appear often. */
            for (i = s; i < r; i++)
                text_buf[i] = fillByte;
            /* Read F bytes into the last F bytes of the buffer text of size zero. */
            for (len = 0; len < LZSSConsts.F && ((c = byteReader.ReadByte()) != EOF || end > (ulong)byteReader.Position); len++)
                text_buf[r + len] = (byte)c;
            if ((textsize = (uint)len) == 0) //  
                return new byte[0];
            /* Insert the F strings,
             * each of which begins with one or more 'space' characters.
             * Note the order in which these strings are inserted.
             * This way, degenerate trees will be less likely to occur. */
            for (i = 1; i <= LZSSConsts.F; i++)
                InsertNode(r - i);
            /* Finally, insert the whole string just read. The
             * global variables match_length and match_position are set. */
            InsertNode(r);
            do
            {
                /* match_length may be spuriously long near the end of text. */
                if (match_length > len)
                    match_length = len;
                if (match_length <= LZSSConsts.THRESHOLD)
                {
                    match_length = 1; // Not long enough match. Send one byte. 
                    code_buf[0] |= mask; // 'send one byte' flag 
                    code_buf[code_buf_ptr++] = text_buf[r]; // Send uncoded. 
                }
                else
                {
                    /* Send position and length pair. Note match_length > THRESHOLD. */
                    code_buf[code_buf_ptr++] = (byte)match_position;
                    code_buf[code_buf_ptr++] = (byte)(((match_position >> 4) & 0xf0) | (match_length - (LZSSConsts.THRESHOLD + 1)));
                }
                /* Shift mask left one bit. */
                if ((mask <<= 1) == 0)
                {
                    /* Send at most 8 units of code together. */
                    for (i = 0; i < code_buf_ptr; i++)
                        byteWriter.Add(code_buf[i]);
                    codesize += (uint)code_buf_ptr;
                    code_buf[0] = 0;
                    code_buf_ptr = mask = 1;
                }
                last_match_length = match_length;
                for (i = 0; i < last_match_length && ((c = byteReader.ReadByte()) != EOF || end > (ulong)byteReader.Position); i++)
                {
                    /* Delete old strings and read new bytes */
                    DeleteNode(s);
                    text_buf[s] = (byte)c;
                    /* If the position is near the end of buffer,
                     * extend the buffer to make string comparison easier. */
                    if (s < LZSSConsts.F - 1)
                        text_buf[s + LZSSConsts.N] = (byte)c;
                    /* Since this is a ring buffer,
                    increment the position modulo N. */
                    s = (s + 1) & (LZSSConsts.N - 1);
                    r = (r + 1) & (LZSSConsts.N - 1);
                    /* Register the string in text_buf[r..r+F-1] */
                    InsertNode(r);
                }
                if ((textsize += (uint)i) > printcount)
                {
                    //Console.Write("{0,12:D}\r", textsize);
                    printcount += 1024;
                    /* Reports progress each time the textsize exceeds multiples of 1024. */
                }
                while (i++ < last_match_length)
                {
                    /* After the end of text, 
                     * no need to read, 
                     * but buffer may not be empty. */
                    DeleteNode(s);
                    s = (s + 1) & (LZSSConsts.N - 1);
                    r = (r + 1) & (LZSSConsts.N - 1);
                    if (--len > 0)
                        InsertNode(r);
                }
            }
            /* Until length of string to be processed is zero
             * Send remaining code.*/
            while (len > 0); //  
            if (code_buf_ptr > 1)
            {
                for (i = 0; i < code_buf_ptr; i++)
                    byteWriter.Add(code_buf[i]);
                codesize += (uint)code_buf_ptr;
            }
            #if DEBUG
            Console.Write("In : {0:D} bytes\n", textsize); // Encoding is done. 
            Console.Write("Out: {0:D} bytes\n", codesize);
            Console.Write("Out/In: {0:f3}\n", (double)codesize / textsize);
            #endif
            return byteWriter.ToArray();
        }

        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode until the end of the stream.
        /// </summary>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader) { return Decode(byteReader, 0, 0, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode from given position until the end of the stream.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, long position) { return Decode(byteReader, position, 0, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode until the end of the stream.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, byte fillByte) { return Decode(byteReader, 0, fillByte, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode until the end of the stream or chosen position (end of stream will be prioritized).
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, ulong end) { return Decode(byteReader, 0, 0, end); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode from given position until the end of the stream.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, long position, byte fillByte) { return Decode(byteReader, position, fillByte, (ulong)byteReader.Length); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode from given position until chosen position.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, long position, ulong end) { return Decode(byteReader, position, 0, end); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode until the chosen position.
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, byte fillByte, ulong end) { return Decode(byteReader, 0, fillByte, end); }
        /// <summary>
        /// LZSS Decoding (or decompression) based on a stream. Will decode from given position until the end of the stream or chosen position (end of stream will be prioritized).
        /// </summary>
        /// <param name="byteReader">The stream to read from.</param>
        /// <param name="position">The positon in the stream to start at. Default 0.</param>
        /// <param name="fillByte">Byte to clear the buffer with (byte that will appear often. for instance: 0x00, 0x20, 0xFF).</param>
        /// <param name="end">Position in stream where encoding will end. If the stream ends before this position, the decoding will be forced to end.</param>
        /// <returns>The decoded stream of bytes.</returns>
        public static byte[] Decode(Stream byteReader, long position, byte fillByte, ulong end)
        /* Just the reverse of Encode(). */
        {
            int i;
            int j;
            int k;
            int r;
            int c;
            uint flags;
            List<byte> byteWriter = new List<byte>();
            byteReader.Position = position;

            for (i = 0; i < LZSSConsts.N - LZSSConsts.F; i++)
                text_buf[i] = fillByte;
            r = LZSSConsts.N - LZSSConsts.F;
            flags = 0;
            for (; ; )
            {
                if (((flags >>= 1) & 256) == 0)
                {
                    if ((c = byteReader.ReadByte()) == EOF || end < (ulong)byteReader.Position)
                        break;
                    /* Uses higher byte cleverly to count eight. */
                    flags = (uint)c | 0xff00;
                }
                if ((flags & 1) != 0)
                {
                    if ((c = byteReader.ReadByte()) == EOF || end < (ulong)byteReader.Position)
                        break;
                    byteWriter.Add((byte)c);
                    text_buf[r++] = (byte)c;
                    r &= (LZSSConsts.N - 1);
                }
                else
                {
                    if ((i = byteReader.ReadByte()) == EOF || end < (ulong)byteReader.Position)
                        break;
                    if ((j = byteReader.ReadByte()) == EOF || end < (ulong)byteReader.Position)
                        break;
                    i |= ((j & 0xf0) << 4);
                    j = (j & 0x0f) + LZSSConsts.THRESHOLD;
                    for (k = 0; k <= j; k++)
                    {
                        c = text_buf[(i + k) & (LZSSConsts.N - 1)];
                        byteWriter.Add((byte)c);
                        text_buf[r++] = (byte)c;
                        r &= (LZSSConsts.N - 1);
                    }
                }
            }
            return byteWriter.ToArray();
        }
    }

    internal static class LZSSConsts
    {
        public const int N = 4096;
        public const int F = 18;
        public const int THRESHOLD = 2;
        public const int NF1 = N + F - 1;
    }
}