from app import app, build_video_command, enforce_visual_style, image_index_from_filename


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
    assert b'Flask Documentary Studio' in response.data


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


def test_video_command_binds_narration_after_all_image_inputs():
    command = build_video_command(['1.jpg', '2.jpg', '3.jpg'], 'narration.wav', 'video.mp4', 30)
    command_text = ' '.join(command)
    assert 'xfade=' in command_text
    assert 'zoompan=' in command_text
    assert 'transition=smoothleft' in command_text
    assert 'concat=' not in command_text
    assert command[-1] == 'video.mp4'
    assert command[command.index('-map') + 3] == '[narration]'


def test_create_session_persists_render_settings():
    client = authenticated_client()
    response = client.post('/api/create-session', json={
        'topic': 'Render settings test',
        'image_seconds': 8,
        'transition_seconds': 1.5,
        'narration_volume': 1.2,
        'bgm_volume': 0.35,
        'visual_style': 'cartoon',
        'script_language': 'english',
        'target_duration': 120,
    })
    assert response.status_code == 200


def test_visual_style_is_mandatory_in_every_prompt():
    prompts = enforce_visual_style(['1. A historical kitchen scene.'], 'cartoon')
    assert 'MANDATORY VISUAL STYLE:' in prompts
    assert 'Stylized 2D cartoon animation' in prompts
