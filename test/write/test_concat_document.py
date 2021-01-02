import logging
from pathlib import Path

from ptext.pdf.document import Document
from ptext.pdf.pdf import PDF
from test.base_test import BaseTest

logging.basicConfig(filename="../write/test_concat_document.log", level=logging.DEBUG)


class TestConcatDocument(BaseTest):
    def __init__(self, methodName="runTest"):
        super().__init__(methodName)
        self.output_dir = Path("../write/concat")
        self.input_file_b = self.input_dir / "0200.pdf"

    def test_single_document(self):
        self.input_file = self.input_dir / "0200.pdf"
        super().test_single_document()

    def test_against_previous_fails(self):
        super().test_against_previous_fails()

    def test_against_entire_corpus(self):
        super().test_against_entire_corpus()

    def _test_document(self, file):
        if "0287" in file.stem:
            return
        if "0190" in file.stem:
            return
        if "0399" in file.stem:
            return
        # create output directory if it does not exist yet
        if not self.output_dir.exists():
            self.output_dir.mkdir()

        # determine output location
        out_file = self.output_dir / (file.stem + "_out.pdf")

        # attempt to read PDF
        doc_a = None
        with open(file, "rb") as in_file_handle:
            print("\treading (1) ..")
            doc_a = PDF.loads(in_file_handle)

        # attempt to read PDF
        with open(self.input_file_b, "rb") as in_file_handle_b:
            print("\treading (2) ..")
            doc_b = PDF.loads(in_file_handle_b)

        # concat all pages to same document
        doc_c = Document()
        for i in range(0, int(doc_a.get_document_info().get_number_of_pages())):
            doc_c.append_page(doc_a.get_page(i))
        for i in range(0, int(doc_b.get_document_info().get_number_of_pages())):
            doc_c.append_page(doc_b.get_page(i))

        # attempt to store PDF
        with open(out_file, "wb") as out_file_handle:
            print("\twrite ..")
            PDF.dumps(out_file_handle, doc_c)
