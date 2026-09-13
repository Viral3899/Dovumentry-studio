import wave

from app.main import app
from app.services.prompts import enforce_visual_style
from app.services.session import image_index_from_filename
from app.utils.constants import VISUAL_STYLES
import app.services.session as session_module
import app.services.video as video_module


def authenticated_client():
    client = app.test_client()
    response = client.post('/api/auth/login', json={
        'username': 'demo',
        'password': 'demo123',
        'role': 'admin',
    })
    assert response.status_code == 200
    return client


def test_homepage_renders():
    client = app.test_client()
    response = client.get('/')
    assert response.status_code == 200
    assert b'Documentary Studio' in response.data


def test_topic_creation_requires_topic():
    client = authenticated_client()
    response = client.post('/api/create-session', json={})
    assert response.status_code == 400


def test_demo_login_uses_database_account():
    client = authenticated_client()
    response = client.get('/api/auth/me')
    assert response.json['authenticated'] is True
    assert response.json['username'] == 'demo'
    assert response.json['role'] == 'admin'


def test_image_index_accepts_timestamped_generated_filename():
    assert image_index_from_filename('1.jpeg_202609071015') == 1
    assert image_index_from_filename('12-before.jpg') == 12
    assert image_index_from_filename('cover.jpg') == 0


def test_video_pipeline_uses_xfade_and_mixed_audio(monkeypatch, tmp_path):
    captured = {}
    monkeypatch.setattr(video_module, 'get_duration', lambda path: 30.0)
    bgm = tmp_path / 'score.mp3'
    bgm.write_bytes(b'x')
    import app.utils.paths as paths_module
    monkeypatch.setattr(paths_module, 'BGM_DIR', tmp_path)

    def fake_run(cmd, **kwargs):
        class Result:
            stdout = 'libx264'
            stderr = ''
            returncode = 0
        if isinstance(cmd, list) and '-encoders' in cmd:
            return Result()
        captured['cmd'] = cmd
        return Result()

    monkeypatch.setattr('subprocess.run', fake_run)

    from app.services.session import get_session_dir
    from pathlib import Path
    session_dir = get_session_dir('test_session')
    session_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / 'images').mkdir(exist_ok=True)
    for i in range(1, 4):
        img = session_dir / 'images' / f'{i}.jpg'
        img.write_bytes(b'fake')

    audio = session_dir / 'narration.wav'
    audio.write_bytes(b'fake')

    output = session_dir / 'output.mp4'
    video_module.build_video_pipeline(
        sorted((session_dir / 'images').glob('*.jpg')),
        audio, output,
        image_seconds=5, transition_seconds=1,
    )

    assert captured['cmd'] is not None
    cmd = captured['cmd']
    assert '-filter_complex' in cmd
    filter_idx = cmd.index('-filter_complex')
    filter_graph = cmd[filter_idx + 1]
    assert 'xfade=transition=fade' in filter_graph
    assert 'amix=inputs=2' in filter_graph
    assert 'libx264' in cmd or 'h264_nvenc' in cmd


def test_create_session_persists_render_settings():
    client = authenticated_client()
    resp = client.post('/api/create-session', json={
        'topic': 'Test Topic',
        'target_duration': 120,
        'transition_seconds': 2.5,
        'narration_volume': 2.0,
        'bgm_volume': 0.5,
    })
    assert resp.status_code == 200
    session_id = resp.json['session_id']
    session_dir = session_module.get_session_dir(session_id)
    state = session_module.load_state(session_dir)
    assert state['target_duration'] == 120
    assert state['transition_seconds'] == 2.5
    assert state['narration_volume'] == 2.0
    assert state['bgm_volume'] == 0.5


def test_visual_style_is_mandatory_in_every_prompt():
    prompts = ["First scene description.", "Second scene with details."]
    styled = enforce_visual_style(prompts, "photorealistic")
    for i, prompt in enumerate(prompts, 1):
        assert f"{i}. {prompt}" in styled
        assert "MANDATORY VISUAL STYLE:" in styled
        assert VISUAL_STYLES["photorealistic"] in styled


def test_audio_generation_uses_edge_tts_when_gemini_fails(monkeypatch):
    client = authenticated_client()
    session_response = client.post('/api/create-session', json={'topic': 'Edge TTS fallback test'})
    assert session_response.status_code == 200
    session_id = session_response.json['session_id']
    session_dir = session_module.get_session_dir(session_id)
    (session_dir / 'documentary_script.txt').write_text('\u092f\u0939 \u090f\u0915 \u092a\u0930\u0940\u0915\u094d\u0937\u0923 \u0939\u0948\u0964', encoding='utf-8')

    from app.services.providers import ProviderRequiredError
    def raise_provider_required(*args, **kwargs):
        raise ProviderRequiredError("gemini", "Gemini unavailable", "default_voice")
    
    monkeypatch.setattr('app.services.audio.generate_real_audio', raise_provider_required)

    def fake_edge_tts(path, script, voice):
        with wave.open(str(path), 'wb') as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(22050)
            output.writeframes(b'\x00\x00' * 22050)
        return path

    monkeypatch.setattr('app.services.audio.generate_local_audio', fake_edge_tts)
    monkeypatch.setattr('app.services.session.get_duration', lambda path: 1.0)

    response = client.post('/api/generate-audio', json={'session_id': session_id, 'use_default_voice': True})
    assert response.status_code == 200
    assert response.json['success'] is True


def test_extract_json_repairs_truncated_topic_array():
    from app.services.social import _extract_json
    truncated = '{"topics":[{"topic":"Test Topic 1","hook":"Hook 1","angle":"Angle 1","why":"Why 1","keywords":["kw1","kw2"]},{"topic":"Test Topic 2","hook":"Hook 2"'
    result = _extract_json(truncated)
    assert result is not None
    assert isinstance(result, dict)
    assert 'topics' in result
    assert len(result['topics']) >= 1
    assert result['topics'][0]['topic'] == 'Test Topic 1'


def test_extract_json_closes_unterminated_string():
    from app.services.social import _extract_json
    bad = '{"topic":"Test Topic","hook":"Hook with "unclosed quote","angle":"Angle","why":"Why","keywords":[]}'
    result = _extract_json(bad)
    assert result is not None
    assert result.get('topic') == 'Test Topic'


def test_repair_ignores_braces_inside_strings():
    from app.services.social import _repair_truncated_array
    text = '{"topic":"Has {braces} inside","hook":"Hook","angle":"Angle","why":"Why","keywords":[]}'
    items = _repair_truncated_array(text)
    assert len(items) == 1
    assert items[0]['topic'] == 'Has {braces} inside'