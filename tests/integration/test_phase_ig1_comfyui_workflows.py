"""Phase IG-1 — ComfyUI identity-consistent workflow templating.

Pure (no live ComfyUI): validates workflow resolution + placeholder
substitution and that every shipped template parses to valid JSON after
substitution, with the face reference injected into the LoadImage node.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.image_providers.base import (
    ImageGenerationInput,
    ProviderUnavailableError,
)
from app.services.image_providers.local_wrapper_stub import (
    LocalWrapperImageProviderStub,
)

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / "workflows" / "comfyui"
ALL_TEMPLATES = sorted(p.stem for p in WORKFLOW_DIR.glob("*.json"))
CONSISTENT_TEMPLATES = [t for t in ALL_TEMPLATES if "consistent" in t]


def _comfyui_provider() -> LocalWrapperImageProviderStub:
    return LocalWrapperImageProviderStub.build(
        provider_id="comfyui_local",
        display_name="ComfyUI",
        default_model=None,
        base_url_env="COMFYUI_BASE_URL",
        models_root_env="COMFYUI_MODELS_ROOT",
        runtime_label="ComfyUI",
    )


def _input(**kw) -> ImageGenerationInput:
    base = dict(
        prompt='a "synthetic" persona, autumn park',
        negative_prompt="different person, distorted face",
        model_id=None,
        seed=42,
        width=768,
        height=1024,
        steps=20,
        guidance_scale=4.0,
        reference_image_path=None,
    )
    base.update(kw)
    return ImageGenerationInput(**base)


def test_templates_exist():
    assert "sdxl_initial" in ALL_TEMPLATES
    assert "sdxl_instantid_consistent" in ALL_TEMPLATES
    assert "pulid_flux_consistent" in ALL_TEMPLATES


@pytest.mark.parametrize("template_name", ALL_TEMPLATES)
def test_every_template_parses_after_substitution(template_name):
    template = (WORKFLOW_DIR / f"{template_name}.json").read_text(encoding="utf-8")
    wf = LocalWrapperImageProviderStub._build_workflow_dict(
        template, _input(), seed_val=42, face_ref_name="face.png", body_ref_name="body.png"
    )
    assert isinstance(wf, dict) and wf, "workflow must be a non-empty dict"
    # No placeholder may survive substitution.
    blob = json.dumps(wf)
    for ph in ("__PROMPT__", "__NEGATIVE__", "__SEED__", "__WIDTH__",
               "__HEIGHT__", "__STEPS__", "__CFG__", "__FACE_REF__", "__BODY_REF__"):
        assert ph not in blob, f"{ph} not substituted in {template_name}"


@pytest.mark.parametrize("template_name", CONSISTENT_TEMPLATES)
def test_consistent_templates_inject_face_reference(template_name):
    template = (WORKFLOW_DIR / f"{template_name}.json").read_text(encoding="utf-8")
    wf = LocalWrapperImageProviderStub._build_workflow_dict(
        template, _input(), seed_val=7, face_ref_name="canonical_face.png", body_ref_name=""
    )
    load_nodes = [
        n for n in wf.values()
        if isinstance(n, dict) and n.get("class_type") == "LoadImage"
    ]
    assert load_nodes, f"{template_name} must have a LoadImage node for the face ref"
    assert any(
        n["inputs"].get("image") == "canonical_face.png" for n in load_nodes
    ), f"{template_name} did not inject the face reference into LoadImage"


def test_prompt_with_quotes_keeps_valid_json():
    template = (WORKFLOW_DIR / "sdxl_initial.json").read_text(encoding="utf-8")
    wf = LocalWrapperImageProviderStub._build_workflow_dict(
        template,
        _input(prompt='a woman who said "hello" \\ backslash'),
        seed_val=1, face_ref_name="", body_ref_name="",
    )
    # The CLIPTextEncode node must carry the exact prompt, unescaped.
    texts = [
        n["inputs"]["text"]
        for n in wf.values()
        if isinstance(n, dict) and n.get("class_type") == "CLIPTextEncode"
    ]
    assert any('said "hello"' in t for t in texts)


def test_resolve_workflow_template_missing_raises(monkeypatch, tmp_path):
    monkeypatch.setenv("COMFYUI_WORKFLOW_DIR", str(tmp_path))
    monkeypatch.delenv("COMFYUI_WORKFLOW_PATH", raising=False)
    prov = _comfyui_provider()
    with pytest.raises(ProviderUnavailableError) as ei:
        prov._resolve_workflow_template(_input(workflow_name="does_not_exist"))
    assert ei.value.error_code == "provider_not_configured"


def test_resolve_workflow_template_reads_from_dir(monkeypatch):
    monkeypatch.setenv("COMFYUI_WORKFLOW_DIR", str(WORKFLOW_DIR))
    prov = _comfyui_provider()
    text = prov._resolve_workflow_template(_input(workflow_name="sdxl_initial"))
    assert "CheckpointLoaderSimple" in text


def test_resolve_workflow_template_blocks_path_traversal(monkeypatch, tmp_path):
    monkeypatch.setenv("COMFYUI_WORKFLOW_DIR", str(WORKFLOW_DIR))
    prov = _comfyui_provider()
    # "../../etc/passwd" must be sanitised to a bare stem under the dir.
    with pytest.raises(ProviderUnavailableError):
        prov._resolve_workflow_template(_input(workflow_name="../../../etc/passwd"))
