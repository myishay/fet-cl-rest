"""Tests for the FetOptions model and its argv rendering."""

import pytest
from pydantic import ValidationError

from app.fet.options import CsvFieldSeparator, CsvQuotes, FetOptions


def test_empty_options_render_nothing():
    assert FetOptions().to_args() == []


def test_core_options_render_name_value():
    opts = FetOptions(timelimitseconds=120, htmllevel=4, language="de", verbose=True)
    args = set(opts.to_args())
    assert "--timelimitseconds=120" in args
    assert "--htmllevel=4" in args
    assert "--language=de" in args
    assert "--verbose=true" in args


def test_booleans_render_lowercase_true_false():
    opts = FetOptions(writetimetablesxml=False, exportcsv=True)
    args = set(opts.to_args())
    assert "--writetimetablesxml=false" in args
    assert "--exportcsv=true" in args


def test_enum_csv_options_render_value():
    opts = FetOptions(
        exportcsv=True,
        quotescsv=CsvQuotes.singlequotes,
        fieldseparatorcsv=CsvFieldSeparator.semicolon,
    )
    args = set(opts.to_args())
    assert "--quotescsv=singlequotes" in args
    assert "--fieldseparatorcsv=semicolon" in args


def test_invalid_htmllevel_rejected():
    with pytest.raises(ValidationError):
        FetOptions(htmllevel=9)


def test_invalid_language_rejected():
    with pytest.raises(ValidationError):
        FetOptions(language="klingon")


def test_unknown_field_forbidden():
    with pytest.raises(ValidationError):
        FetOptions(not_a_real_flag=True)


def test_extra_flags_passthrough():
    opts = FetOptions(extra_flags={"subgroupsdayshvprintsubjectsnames": "true"})
    assert "--subgroupsdayshvprintsubjectsnames=true" in opts.to_args()


def test_extra_flags_strip_leading_dashes():
    opts = FetOptions(extra_flags={"--printroomscomments": "false"})
    assert "--printroomscomments=false" in opts.to_args()


def test_extra_flags_cannot_override_managed():
    with pytest.raises(ValidationError):
        FetOptions(extra_flags={"inputfile": "/etc/passwd"})


def test_partial_seeds_rejected():
    with pytest.raises(ValidationError):
        FetOptions(randomseeds10=1)


def test_all_seeds_accepted():
    opts = FetOptions(
        randomseeds10=1, randomseeds11=2, randomseeds12=3,
        randomseeds20=4, randomseeds21=5, randomseeds22=6,
    )
    args = set(opts.to_args())
    assert "--randomseeds10=1" in args
    assert "--randomseeds22=6" in args


def test_all_zero_seeds_rejected():
    with pytest.raises(ValidationError):
        FetOptions(
            randomseeds10=0, randomseeds11=0, randomseeds12=0,
            randomseeds20=0, randomseeds21=0, randomseeds22=0,
        )
