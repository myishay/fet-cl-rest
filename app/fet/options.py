"""Typed model of fet-cl generation options.

Maps the command-line flags of ``fet-cl`` (FET 7.8.x) to a validated Pydantic
model and renders them back to the ``--name=value`` argv form FET expects.

``inputfile`` and ``outputdir`` are intentionally NOT modelled here: they are
managed by the runner (it controls where the uploaded file and results live).
This model covers the *generation* options a caller may legitimately tune.

Flags are documented at https://lalescu.ro/liviu/fet and in ``fet-cl --help``.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class CsvQuotes(str, Enum):
    doublequotes = "doublequotes"
    singlequotes = "singlequotes"
    none = "none"


class CsvFieldSeparator(str, Enum):
    comma = "comma"
    semicolon = "semicolon"
    verticalbar = "verticalbar"


# Allowed UI/output languages accepted by ``--language=`` (FET 7.8.x).
ALLOWED_LANGUAGES = {
    "ar", "bg", "bs", "ca", "cs", "da", "de", "el", "en_GB", "en_US", "es",
    "eu", "fa", "fr", "gl", "he", "hu", "id", "it", "ja", "lt", "mk", "ms",
    "nl", "pl", "pt_BR", "ro", "ru", "si", "sk", "sq", "sr", "tr", "uk", "uz",
    "vi", "zh_CN", "zh_TW",
}


def _fmt(value: object) -> str:
    """Render a Python value the way fet-cl expects on the command line."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


class FetOptions(BaseModel):
    """Validated subset (plus passthrough) of fet-cl generation options.

    All fields are optional; ``None`` means "let fet-cl use its default".
    Anything not modelled explicitly can be supplied via ``extra_flags`` to
    retain full parity with the CLI.
    """

    model_config = {"extra": "forbid"}

    # --- Core ---------------------------------------------------------------
    timelimitseconds: Optional[int] = Field(
        default=None, ge=1,
        description="Stop generation after this many seconds (FET default ~infinite).",
    )
    htmllevel: Optional[int] = Field(
        default=None, ge=0, le=7,
        description="Detail level of generated HTML timetables (0-7, FET default 2).",
    )
    language: Optional[str] = Field(
        default=None,
        description="UI/output language code, e.g. en_US, de, fr (FET default en_US).",
    )
    verbose: Optional[bool] = Field(
        default=None, description="Print extra generation/progress messages.",
    )

    # --- Reproducible random seeds (all six required together) --------------
    randomseeds10: Optional[int] = Field(default=None, ge=0, le=4294967086)
    randomseeds11: Optional[int] = Field(default=None, ge=0, le=4294967086)
    randomseeds12: Optional[int] = Field(default=None, ge=0, le=4294967086)
    randomseeds20: Optional[int] = Field(default=None, ge=0, le=4294944442)
    randomseeds21: Optional[int] = Field(default=None, ge=0, le=4294944442)
    randomseeds22: Optional[int] = Field(default=None, ge=0, le=4294944442)

    # --- Which timetable files to write (FET defaults all true) -------------
    writetimetableconflicts: Optional[bool] = None
    writetimetablesstatistics: Optional[bool] = None
    writetimetablesxml: Optional[bool] = None
    writetimetablesdayshorizontal: Optional[bool] = None
    writetimetablesdaysvertical: Optional[bool] = None
    writetimetablestimehorizontal: Optional[bool] = None
    writetimetablestimevertical: Optional[bool] = None
    writetimetablessubgroups: Optional[bool] = None
    writetimetablesgroups: Optional[bool] = None
    writetimetablesyears: Optional[bool] = None
    writetimetablesteachers: Optional[bool] = None
    writetimetablesteachersfreeperiods: Optional[bool] = None
    writetimetablesbuildings: Optional[bool] = None
    writetimetablesrooms: Optional[bool] = None
    writetimetablessubjects: Optional[bool] = None
    writetimetablesactivitytags: Optional[bool] = None
    writetimetablesactivities: Optional[bool] = None

    # --- HTML content toggles ----------------------------------------------
    printsubjects: Optional[bool] = None
    printactivitytags: Optional[bool] = None
    printteachers: Optional[bool] = None
    printstudents: Optional[bool] = None
    printrooms: Optional[bool] = None
    printnotavailable: Optional[bool] = None
    printbreak: Optional[bool] = None
    sortsubgroups: Optional[bool] = None
    dividetimeaxisbydays: Optional[bool] = None
    duplicateverticalheaders: Optional[bool] = None
    printsimultaneousactivities: Optional[bool] = None
    printdetailedtimetables: Optional[bool] = None
    printdetailedteachersfreeperiodstimetables: Optional[bool] = None
    showvirtualrooms: Optional[bool] = None

    # --- CSV export ---------------------------------------------------------
    exportcsv: Optional[bool] = None
    overwritecsv: Optional[bool] = None
    firstlineisheadingcsv: Optional[bool] = None
    quotescsv: Optional[CsvQuotes] = None
    fieldseparatorcsv: Optional[CsvFieldSeparator] = None

    # --- Warning toggles ----------------------------------------------------
    warnifusinggroupactivitiesininitialorder: Optional[bool] = None
    warnsubgroupswiththesameactivities: Optional[bool] = None
    warnifusingactivitiesnotfixedtimefixedspacevirtualroomsrealrooms: Optional[bool] = None
    warnifusingmaxhoursdailywithlessthan100percentweight: Optional[bool] = None

    # --- Generic passthrough for the long per-view formatting families ------
    extra_flags: dict[str, str] = Field(
        default_factory=dict,
        description=(
            "Any additional fet-cl flag as name->value, e.g. "
            '{"subgroupsdayshvprintsubjectsnames": "true"}. Names must not '
            "start with '--'; values are passed through verbatim."
        ),
    )

    @field_validator("language")
    @classmethod
    def _check_language(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in ALLOWED_LANGUAGES:
            raise ValueError(
                f"Unsupported language {v!r}. Allowed: {sorted(ALLOWED_LANGUAGES)}"
            )
        return v

    @field_validator("extra_flags")
    @classmethod
    def _check_extra_flags(cls, v: dict[str, str]) -> dict[str, str]:
        reserved = {"inputfile", "outputdir", "version", "help"}
        for name in v:
            key = name.lstrip("-")
            if not key or any(c.isspace() for c in key):
                raise ValueError(f"Invalid extra flag name: {name!r}")
            if key in reserved:
                raise ValueError(
                    f"Flag {key!r} is managed by the service and cannot be overridden."
                )
        return v

    @model_validator(mode="after")
    def _check_seeds_together(self) -> "FetOptions":
        seeds = [
            self.randomseeds10, self.randomseeds11, self.randomseeds12,
            self.randomseeds20, self.randomseeds21, self.randomseeds22,
        ]
        provided = [s is not None for s in seeds]
        if any(provided) and not all(provided):
            raise ValueError(
                "All six randomseeds10/11/12/20/21/22 must be supplied together."
            )
        if all(provided):
            if not any(seeds[:3]):
                raise ValueError("randomseeds10/11/12 must not all be zero.")
            if not any(seeds[3:]):
                raise ValueError("randomseeds20/21/22 must not all be zero.")
        return self

    def to_args(self) -> list[str]:
        """Render the modelled options as a list of ``--name=value`` strings.

        Only fields the caller actually set are emitted; everything else is
        left to fet-cl's own defaults.
        """
        args: list[str] = []
        data = self.model_dump(exclude_none=True, exclude={"extra_flags"})
        for name, value in data.items():
            args.append(f"--{name}={_fmt(value)}")
        for name, value in self.extra_flags.items():
            key = name.lstrip("-")
            args.append(f"--{key}={value}")
        return args
