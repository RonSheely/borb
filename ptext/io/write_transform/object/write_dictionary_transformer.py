import typing
from typing import Optional

from PIL.Image import Image  # type: ignore [import]

from ptext.io.read_transform.types import (
    AnyPDFType,
    Dictionary,
    List,
    Reference,
    Stream,
)
from ptext.io.write_transform.write_base_transformer import (
    WriteBaseTransformer,
    TransformerWriteContext,
)


class WriteDictionaryTransformer(WriteBaseTransformer):
    def __init__(self):
        self.queue: typing.List[AnyPDFType] = []

    def can_be_transformed(self, any: AnyPDFType):
        return isinstance(any, Dictionary)

    def transform(
        self,
        object_to_transform: AnyPDFType,
        context: Optional[TransformerWriteContext] = None,
    ):
        assert isinstance(object_to_transform, Dictionary)
        assert context is not None
        assert context.destination is not None
        assert context.destination

        # output value
        out_value = Dictionary()

        # objects to turn into reference
        queue: typing.List[AnyPDFType] = []
        for k, v in object_to_transform.items():
            if (
                isinstance(v, Dictionary)
                or isinstance(v, List)
                or isinstance(v, Stream)
                or isinstance(v, Image)
            ):
                out_value[k] = self.get_reference(v, context)
                queue.append(v)
            else:
                out_value[k] = v

        # start object if needed
        started_object = False
        ref = object_to_transform.get_reference()  # type: ignore [attr-defined]
        if ref is not None:
            assert isinstance(ref, Reference)
            if ref in context.duplicate_references:
                return
            if ref.object_number is not None and ref.byte_offset is None:
                started_object = True
                self.start_object(object_to_transform, context)
            context.duplicate_references.append(ref)

        # write dictionary at current location
        context.destination.write(bytes("<<", "latin1"))
        N = len(out_value.items())
        for i, (k, v) in enumerate(out_value.items()):
            self.get_root_transformer().transform(k, context)
            context.destination.write(bytes(" ", "latin1"))
            self.get_root_transformer().transform(v, context)
            if i != N - 1:
                context.destination.write(bytes(" ", "latin1"))
        context.destination.write(bytes(">>\n", "latin1"))

        # end object if needed
        if started_object:
            self.end_object(object_to_transform, context)

        for e in queue:
            self.get_root_transformer().transform(e, context)

        # return
        return out_value
