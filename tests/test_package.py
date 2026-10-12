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


def test_core_has_no_runtime_dependencies():
    requirements = metadata.requires("fluteomr") or []

    assert all('extra == "dev"' in requirement for requirement in requirements)
