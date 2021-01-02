import io
from decimal import Decimal
from typing import Optional, Union

from ptext.exception.pdf_exception import PDFTypeError, PDFValueError
from ptext.io.filter.stream_decode_util import decode_stream
from ptext.io.read_transform.types import Reference, Stream, Dictionary, List
from ptext.io.tokenize.high_level_tokenizer import HighLevelTokenizer
from ptext.pdf.xref.xref import XREF


class StreamXREF(XREF):
    """
    Beginning with PDF 1.5, cross-reference information may be stored in a cross-reference stream instead of in a
    cross-reference table. Cross-reference streams provide the following advantages:
    • A more compact representation of cross-reference information
    • The ability to access compressed objects that are stored in object streams (see 7.5.7, "Object Streams")
    and to allow new cross-reference entry types to be added in the future
    Cross-reference streams are stream objects (see 7.3.8, "Stream Objects"), and contain a dictionary and a data
    stream. Each cross-reference stream contains the information equivalent to the cross-reference table
     (see 7.5.4, "Cross-Reference Table") and trailer (see 7.5.5, "File Trailer") for one cross-reference section.
    """

    def __init__(self, initial_offset: Optional[int] = None):
        super().__init__()
        self.initial_offset = initial_offset

    def read(
        self,
        io_source: Union[io.BufferedIOBase, io.RawIOBase],
        tokenizer: HighLevelTokenizer,
        initial_offset: Optional[int] = None,
    ) -> "XREF":

        if initial_offset is not None:
            io_source.seek(initial_offset)
        else:
            self._seek_to_xref_token(io_source, tokenizer)

        xref_stream = tokenizer.read_object()
        if not isinstance(xref_stream, Stream):
            raise PDFTypeError(
                received_type=xref_stream.__class__,
                expected_type=Stream,
            )

        # check widths
        if "W" not in xref_stream:
            raise PDFTypeError(expected_type=list, received_type=None)
        if any(
            [
                not isinstance(xref_stream["W"][x], Decimal)
                for x in range(0, len(xref_stream["W"]))
            ]
        ):
            raise PDFValueError(
                expected_value_description="[Decimal]",
                received_value_description=str([str(x) for x in xref_stream["W"]]),
            )

        # decode widths
        widths = [int(xref_stream["W"][x]) for x in range(0, len(xref_stream["W"]))]
        total_entry_width = sum(widths)

        # parent
        document = self.get_root()  # type: ignore [attr-defined]

        # list of references
        indirect_references = [
            Reference(
                object_number=0,
                generation_number=65535,
                is_in_use=False,
                document=document,
            )
        ]

        # check size
        if "Size" not in xref_stream:
            raise PDFTypeError(expected_type=Decimal, received_type=None)
        if not isinstance(xref_stream["Size"], Decimal):
            raise PDFTypeError(
                expected_type=Decimal,
                received_type=xref_stream["Size"].__class__,
            )

        # get size
        number_of_objects = int(xref_stream["Size"])

        # index
        index = []
        if "Index" in xref_stream:
            index = xref_stream["Index"]
            assert isinstance(index, List)
            assert len(index) % 2 == 0
            assert isinstance(index[0], Decimal)
            assert isinstance(index[1], Decimal)
        else:
            index = [Decimal(0), Decimal(number_of_objects)]

        # apply filters
        xref_stream = decode_stream(xref_stream)

        # read every range specified in \Index
        xref_stream_decoded_bytes = xref_stream["DecodedBytes"]
        for idx in range(0, len(index), 2):
            start = int(index[idx])
            length = int(index[idx + 1])

            bptr = 0
            for i in range(0, length):

                # object number
                object_number = start + i

                # read type
                type = 1
                if widths[0] > 0:
                    type = 0
                    for j in range(0, widths[0]):
                        type = (type << 8) + (xref_stream_decoded_bytes[bptr] & 0xFF)
                        bptr += 1

                # read field 2
                field2 = 0
                for j in range(0, widths[1]):
                    field2 = (field2 << 8) + (xref_stream_decoded_bytes[bptr] & 0xFF)
                    bptr += 1

                # read field 3
                field3 = 0
                for j in range(0, widths[2]):
                    field3 = (field3 << 8) + (xref_stream_decoded_bytes[bptr] & 0xFF)
                    bptr += 1

                # check type
                assert type in [0, 1, 2]

                pdf_indirect_reference = None
                if type == 0:
                    # type      :The type of this entry, which shall be 0. Type 0 entries define
                    # the linked list of free objects (corresponding to f entries in a
                    # cross-reference table).
                    # field2    : The object number of the next free object
                    # field3    : The generation number to use if this object number is used again
                    pdf_indirect_reference = Reference(
                        document=document,
                        object_number=object_number,
                        byte_offset=field2,
                        generation_number=field3,
                        is_in_use=False,
                    )

                if type == 1:
                    # Type      : The type of this entry, which shall be 1. Type 1 entries define
                    # objects that are in use but are not compressed (corresponding
                    # to n entries in a cross-reference table).
                    # field2    : The byte offset of the object, starting from the beginning of the
                    # file.
                    # field3    : The generation number of the object. Default value: 0.
                    pdf_indirect_reference = Reference(
                        document=document,
                        object_number=object_number,
                        byte_offset=field2,
                        generation_number=field3,
                    )

                if type == 2:
                    # Type      : The type of this entry, which shall be 2. Type 2 entries define
                    # compressed objects.
                    # field2    : The object number of the object stream in which this object is
                    # stored. (The generation number of the object stream shall be
                    # implicitly 0.)
                    # field3    : The index of this object within the object stream.
                    pdf_indirect_reference = Reference(
                        document=document,
                        object_number=object_number,
                        generation_number=0,
                        parent_stream_object_number=field2,
                        index_in_parent_stream=field3,
                    )

                assert pdf_indirect_reference is not None

                # append
                existing_indirect_ref = next(
                    iter(
                        [
                            x
                            for x in indirect_references
                            if x.object_number is not None
                            and x.object_number == Decimal(object_number)
                        ]
                    ),
                    None,
                )
                ref_is_in_reading_state = (
                    existing_indirect_ref is not None
                    and existing_indirect_ref.is_in_use
                    and existing_indirect_ref.generation_number
                    == pdf_indirect_reference.generation_number
                )
                ref_is_first_encountered = existing_indirect_ref is None or (
                    not ref_is_in_reading_state
                    and existing_indirect_ref.document is None
                )

                if ref_is_first_encountered:
                    assert pdf_indirect_reference is not None
                    indirect_references.append(pdf_indirect_reference)
                elif ref_is_in_reading_state:
                    assert existing_indirect_ref is not None
                    assert pdf_indirect_reference is not None
                    existing_indirect_ref.index_in_parent_stream = (
                        pdf_indirect_reference.index_in_parent_stream
                    )
                    existing_indirect_ref.parent_stream_object_number = (
                        pdf_indirect_reference.parent_stream_object_number
                    )

        # add section
        for r in indirect_references:
            self.append(r)

        # initialize trailer
        self["Trailer"] = Dictionary(xref_stream)

        # return
        return self
