"""Strict optimistic-concurrency contract for page notes."""
from pydantic import Field, StrictInt, model_validator

from app.schemas.final_report import ContractModel
from app.schemas.final_report_v2 import EditorialNote, FinalReportModelV2, HASH_PATTERN


class GenerationWarning(ContractModel):
    note_id: str
    message: str


class EditorialSession(ContractModel):
    report: FinalReportModelV2
    revision: StrictInt = Field(ge=0)
    archived_notes: list[EditorialNote] = Field(default_factory=list)
    generation_warnings: list[GenerationWarning] = Field(default_factory=list)


class PrepareEditorialRequest(ContractModel):
    source_hash: str = Field(pattern=HASH_PATTERN)
    expected_revision: StrictInt = Field(ge=0)


class ArchivedNoteReference(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    plan_hash: str = Field(pattern=HASH_PATTERN)
    revision: StrictInt = Field(ge=1)


class SaveEditorialNote(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=16000)
    revision: StrictInt = Field(ge=0)
    from_note: ArchivedNoteReference | None = None

    @model_validator(mode="after")
    def nonblank(self):
        if not self.text.strip():
            raise ValueError("Il commento non può essere vuoto.")
        return self


class GenerateEditorialNote(ContractModel):
    id: str = Field(min_length=1, max_length=128)
    revision: StrictInt = Field(ge=0)


class SaveEditorialNotesRequest(PrepareEditorialRequest):
    plan_hash: str = Field(pattern=HASH_PATTERN)
    notes: list[SaveEditorialNote] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_notes(self):
        if len({note.id for note in self.notes}) != len(self.notes):
            raise ValueError("Gli identificativi dei commenti devono essere univoci.")
        return self


class GenerateEditorialNotesRequest(PrepareEditorialRequest):
    plan_hash: str = Field(pattern=HASH_PATTERN)
    notes: list[GenerateEditorialNote] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def unique_notes(self):
        if len({note.id for note in self.notes}) != len(self.notes):
            raise ValueError("Gli identificativi dei commenti devono essere univoci.")
        return self
