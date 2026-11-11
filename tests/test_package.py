"""Verificações da instalação e dos metadados do pacote."""

from importlib import import_module, metadata


def test_installed_package_is_importable():
    package = import_module("fluteomr")

    assert package.__name__ == "fluteomr"
    assert package.__file__ is not None


def test_installed_distribution_has_expected_metadata():
    distribution = metadata.metadata("fluteomr")

    assert distribution["Name"] == "fluteomr"
    assert distribution["Version"] == "0.1.0"
    assert distribution["Requires-Python"] == ">=3.12"


def test_core_has_only_image_runtime_dependency():
    requirements = metadata.requires("fluteomr") or []

    runtime = [item for item in requirements if "extra ==" not in item]
    assert runtime == ["Pillow==12.3.0"]
    pdf_extra = [item for item in requirements if 'extra == "pdf"' in item]
    assert pdf_extra == ['pypdfium2==5.15.2; extra == "pdf"']
