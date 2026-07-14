class TutorialBook:
    """One 4-byte entry of the mtmag.bin file (one tutorial-menu book).

    Layout (little endian):
        - offset 0 (byte)  : first mmag.bin entry of the book
        - offset 1 (byte)  : last mmag.bin entry of the book
        - offset 2 (uint16): unused padding (preserved as-is on save)

    The tutorial menu pages the magazine viewer between the first and last
    mmag.bin entries (both inclusive)."""

    def __init__(self, book_id, name, first_entry=0, last_entry=0, padding=0):
        self.book_id = book_id
        self.name = name
        self.first_entry = first_entry
        self.last_entry = last_entry
        self.padding = padding  # Bytes 2-3, unused by the game but kept to stay byte-perfect

    @property
    def nb_page(self):
        return self.last_entry - self.first_entry + 1

    def to_bytes(self):
        return bytes([
            self.first_entry & 0xFF,
            self.last_entry & 0xFF,
            self.padding & 0xFF,
            (self.padding >> 8) & 0xFF,
        ])

    def __str__(self):
        return (f"{self.name} (book {self.book_id}): mmag entries "
                f"{self.first_entry}-{self.last_entry} ({self.nb_page} pages)")


class PietManager:
    """mtmag.bin editor logic: the ranges of mmag.bin entries shown by the three
    books of the tutorial menu."""

    NB_BOOK = 3
    NB_BYTE_PER_BOOK = 4
    MAX_MMAG_ENTRY = 68  # mmag.bin has 69 entries (0-68)
    BOOK_NAME_LIST = ["Battle tutorial", "Card rules", "Card icon explanation"]

    def __init__(self):
        self.file_path = ""
        self.books = []

    def load_file(self, file_path):
        self.file_path = file_path
        with open(file_path, "rb") as in_file:
            file_data = in_file.read()
        if len(file_data) != self.NB_BOOK * self.NB_BYTE_PER_BOOK:
            raise ValueError(f"mtmag.bin must be {self.NB_BOOK * self.NB_BYTE_PER_BOOK} bytes, "
                             f"got {len(file_data)}")
        self.books = []
        for book_id in range(self.NB_BOOK):
            offset = book_id * self.NB_BYTE_PER_BOOK
            self.books.append(TutorialBook(
                book_id, self.BOOK_NAME_LIST[book_id],
                first_entry=file_data[offset],
                last_entry=file_data[offset + 1],
                padding=file_data[offset + 2] | (file_data[offset + 3] << 8)))

    def save_file(self, file_path=""):
        if not file_path:
            file_path = self.file_path
        file_data = bytearray()
        for book in self.books:
            file_data.extend(book.to_bytes())
        with open(file_path, "wb") as out_file:
            out_file.write(file_data)

    def set_range(self, book_id, first_entry, last_entry):
        if not 0 <= book_id < self.NB_BOOK:
            raise ValueError(f"Book id must be 0-{self.NB_BOOK - 1}, got {book_id}")
        if not 0 <= first_entry <= self.MAX_MMAG_ENTRY or not 0 <= last_entry <= self.MAX_MMAG_ENTRY:
            raise ValueError(f"mmag entries must be 0-{self.MAX_MMAG_ENTRY}, "
                             f"got {first_entry}-{last_entry}")
        if first_entry > last_entry:
            raise ValueError(f"First entry ({first_entry}) must be <= last entry ({last_entry})")
        self.books[book_id].first_entry = first_entry
        self.books[book_id].last_entry = last_entry
