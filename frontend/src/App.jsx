import { useEffect, useState } from 'react';
import { ArrowLeft, ArrowRight, Check, Clapperboard, Download, FileImage, FileText, Film, LoaderCircle, LogOut, Moon, Mic2, Play, Save, Sparkles, Sun, Upload, WandSparkles } from 'lucide-react';

const steps = [
  { id: 1, label: 'Topic' },
  { id: 2, label: 'Script' },
  { id: 3, label: 'Narration' },
  { id: 4, label: 'Prompts' },
  { id: 5, label: 'Images' },
  { id: 6, label: 'Video' },
];

async function requestJson(url, options = {}) {
  const response = await fetch(url, options);
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.success) throw new Error(result.message || 'Something went wrong.');
  return result;
}

function ActionButton({ children, busy, onClick, disabled, secondary = false, type = 'button' }) {
  return (
    <button className={`action-button ${secondary ? 'secondary' : ''}`} type={type} onClick={onClick} disabled={disabled || busy}>
      {busy ? <LoaderCircle className="spin" size={17} /> : children}
    </button>
  );
}

function hasDevanagari(text) {
  return /[\u0900-\u097F]/.test(text || '');
}

function getInitialTheme() {
  const savedTheme = localStorage.getItem('documentary-theme');
  if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
  return 'dark';
}

function LoginScreen({ onLogin, googleConfigured }) {
  const [role, setRole] = useState('admin');
  const [username, setUsername] = useState('admin');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [authView, setAuthView] = useState('home');

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    try {
      const result = await requestJson('/api/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, password, role }),
      });
      onLogin(result.username, result.role);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const handleGoogleCredential = async (response) => {
    setBusy(true);
    setError('');
    try {
      const result = await requestJson('/api/auth/google', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ credential: response.credential }) });
      onLogin(result.username, result.role);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (!googleConfigured || authView === 'home') return undefined;
    let attempts = 0;
    const renderGoogleButton = () => {
      if (!window.google?.accounts?.id) {
        if (attempts++ < 20) window.setTimeout(renderGoogleButton, 250);
        return;
      }
      window.google.accounts.id.initialize({ client_id: googleConfigured, callback: handleGoogleCredential });
      window.google.accounts.id.renderButton(document.getElementById('google-sign-in'), { theme: 'outline', size: 'large', width: 360, text: 'signin_with' });
    };
    renderGoogleButton();
    return undefined;
  }, [googleConfigured, authView]);

  if (authView === 'home') return <main className="auth-shell"><section className="panel auth-panel auth-home-panel">
    <div className="brand-mark"><Clapperboard size={20} /> DOCUMENTARY STUDIO</div>
    <div className="panel-kicker">A WORKSPACE FOR STORIES</div>
    <h1>Make the story<br /><em>watchable.</em></h1>
    <p className="auth-copy">Create research-driven scripts, narration, visuals, and finished documentaries in one focused studio.</p>
    <div className="auth-home-actions"><ActionButton onClick={() => setAuthView('login')}>Log in <ArrowRight size={17} /></ActionButton><ActionButton secondary onClick={() => setAuthView('signup')}>Sign up <Sparkles size={17} /></ActionButton></div>
  </section></main>;

  return <main className="auth-shell"><section className="panel auth-panel">
    <div className="brand-mark"><Clapperboard size={20} /> DOCUMENTARY STUDIO</div>
    <div className="panel-kicker">{authView === 'login' ? 'STUDIO ACCESS' : 'CREATE YOUR ACCOUNT'}</div>
    <h1>{authView === 'login' ? <>Enter the<br /><em>story room.</em></> : <>Join the<br /><em>story room.</em></>}</h1>
    <p className="auth-copy">{authView === 'login' ? 'Sign in to create, edit, and render documentaries.' : 'Use your approved Google account to join this documentary studio.'}</p>
    {error && <div className="error-banner">{error}</div>}
    {authView === 'login' ? <form onSubmit={submit}>
      <div className="role-switch" role="group" aria-label="Account type"><button type="button" className={role === 'admin' ? 'selected' : ''} onClick={() => setRole('admin')}>Admin</button><button type="button" className={role === 'user' ? 'selected' : ''} onClick={() => setRole('user')}>User</button></div>
      <label>{role === 'admin' ? 'Admin' : 'User'} username<input autoFocus value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" /></label>
      <label>{role === 'admin' ? 'Admin' : 'User'} password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
      <ActionButton type="submit" busy={busy} disabled={!username || !password}>Enter studio <ArrowRight size={17} /></ActionButton>
    </form> : <div className="signup-note"><strong>One studio, approved accounts.</strong><span>Signup is available for the Google email configured by the studio administrator.</span></div>}
    {googleConfigured && <><div className="auth-divider"><span>{authView === 'login' ? 'or continue with Google' : 'continue with Google'}</span></div><div id="google-sign-in" className="google-sign-in" /></>}
    <button className="auth-back-button" type="button" onClick={() => setAuthView(authView === 'login' ? 'home' : 'login')}>{authView === 'login' ? 'Back to home' : 'Already have an account? Log in'}</button>
  </section></main>;
}

function App() {
  const [authenticated, setAuthenticated] = useState(null);
  const [adminUsername, setAdminUsername] = useState('');
  const [userRole, setUserRole] = useState('admin');
  const [googleClientId, setGoogleClientId] = useState('');
  const [theme, setTheme] = useState(getInitialTheme);
  const [topic, setTopic] = useState('');
  const [genre, setGenre] = useState('history');
  const [visualStyle, setVisualStyle] = useState('photorealistic');
  const [scriptLanguage, setScriptLanguage] = useState('hindi');
  const [targetDuration, setTargetDuration] = useState(60);
  const [voice, setVoice] = useState('Iapetus');
  const [session, setSession] = useState(null);
  const [script, setScript] = useState('');
  const [prompts, setPrompts] = useState([]);
  const [generationPrompts, setGenerationPrompts] = useState('');
  const [files, setFiles] = useState([]);
  const [uploadResults, setUploadResults] = useState([]);
  const [uploadSummary, setUploadSummary] = useState(null);
  const [activeStep, setActiveStep] = useState(1);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('Start with a subject worth following.');
  const [audioUrl, setAudioUrl] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [finalVideoUrl, setFinalVideoUrl] = useState('');
  const [musicTrack, setMusicTrack] = useState('');
  const [scriptSaved, setScriptSaved] = useState(false);
  const [imageSeconds, setImageSeconds] = useState(5);
  const [transitionSeconds, setTransitionSeconds] = useState(1);
  const [narrationVolume, setNarrationVolume] = useState(1.5);
  const [bgmVolume, setBgmVolume] = useState(0.2);

  useEffect(() => {
    requestJson('/api/auth/me').then((result) => {
      setAuthenticated(result.authenticated);
      setAdminUsername(result.username || 'admin');
      setUserRole(result.role || 'admin');
      setGoogleClientId(result.google_configured ? (result.google_client_id || '') : '');
    }).catch(() => setAuthenticated(false));
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    localStorage.setItem('documentary-theme', theme);
  }, [theme]);

  if (authenticated === null) return <main className="auth-shell"><div className="auth-loading">Checking studio access...</div></main>;
  if (!authenticated) return <LoginScreen googleConfigured={googleClientId} onLogin={(username, role) => { setAdminUsername(username); setUserRole(role); setAuthenticated(true); }} />;

  const logout = async () => {
    await requestJson('/api/auth/logout', { method: 'POST' });
    setAuthenticated(false);
    setAdminUsername('');
  };
  const toggleTheme = () => setTheme((current) => current === 'light' ? 'dark' : 'light');
  const run = async (key, fn) => {
    setBusy(key);
    setError('');
    try { await fn(); } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  const createSession = (event) => {
    event.preventDefault();
    if (!topic.trim()) { setError('Give the documentary a topic first.'); return; }
    run('session', async () => {
      const result = await requestJson('/api/create-session', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, genre, visual_style: visualStyle, script_language: scriptLanguage, target_duration: targetDuration, image_seconds: imageSeconds, transition_seconds: transitionSeconds, narration_volume: narrationVolume, bgm_volume: bgmVolume }),
      });
      setSession(result);
      setActiveStep(2);
      setMessage('The workspace is ready. Shape the voice of the story next.');
    });
  };

  const generateScript = () => run('script', async () => {
    const result = await requestJson('/api/generate-script', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id, topic, genre, script_language: scriptLanguage, target_duration: targetDuration }),
    });
    setScript(result.script);
    setScriptSaved(false);
    setActiveStep(2);
    setMessage('Script drafted. Review it, save it, then move to narration.');
  });

  const saveScript = () => run('save-script', async () => {
    const result = await requestJson('/api/update-script', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id, script }),
    });
    setScript(result.script);
    setScriptSaved(true);
    setMessage('Hindi script edits saved in the topic project folder.');
  });

  const generateAudio = () => run('audio', async () => {
    const result = await requestJson('/api/generate-audio', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id, voice }),
    });
    setAudioUrl(result.audio_url);
    setActiveStep(3);
    setMessage(`Narration ready at ${result.duration}s. Preview it, then build the visual language.`);
  });

  const generatePrompts = () => run('prompts', async () => {
    const result = await requestJson('/api/generate-prompts', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id, visual_style: visualStyle, image_seconds: imageSeconds, transition_seconds: transitionSeconds, narration_volume: narrationVolume }),
    });
    setPrompts(result.prompts || []);
    setGenerationPrompts(result.generation_prompts || '');
    setActiveStep(4);
    setMessage(`${result.prompts.length} image prompts are ready. Review both prompt documents before uploading images.`);
  });

  const uploadImages = () => run('upload', async () => {
    if (!files.length) throw new Error('Choose the generated images first.');
    const formData = new FormData();
    formData.append('session_id', session.session_id);
    files.forEach((file) => formData.append('files', file));
    const result = await requestJson('/api/upload-images', { method: 'POST', body: formData });
    setUploadResults(result.results || []);
    setUploadSummary({
      uploaded: result.uploaded_count || 0,
      required: result.required_count || prompts.length,
      missing: result.missing_numbers || [],
    });
    const missingNumbers = result.missing_numbers || [];
    setActiveStep(missingNumbers.length ? 5 : 6);
    setMessage(missingNumbers.length
      ? `Upload the missing images: ${missingNumbers.join(', ')}.`
      : 'Images are in sequence. Assemble the film when ready.');
  });

  const buildVideo = () => run('video', async () => {
    const result = await requestJson('/api/build-video', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id, bgm_volume: bgmVolume }),
    });
    setVideoUrl(result.video_url);
    const finalResult = await requestJson('/api/finalize-music', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: session.session_id }),
    });
    setFinalVideoUrl(finalResult.final_video_url);
    setMusicTrack(finalResult.music_track);
    setMessage('The documentary is finished, with a random BGM track mixed at 20%.');
  });

  const downloadUrl = (filename) => session ? `/api/session/${session.session_id}/download/${filename}` : '#';
  const currentVideo = finalVideoUrl || videoUrl;

  return (
    <main className="app-shell">
      <header className="masthead">
        <div className="brand-mark"><Clapperboard size={20} /> DOCUMENTARY STUDIO</div>
        <div className="header-tools">
          <button className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`} title={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}>
            {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
            <span>{theme === 'light' ? 'Dark' : 'Light'}</span>
          </button>
          <div className="header-note">{adminUsername} · {userRole} <button className="logout-button" onClick={logout}><LogOut size={13} /> Sign out</button><span>•</span> {session ? session.session_id.split('-')[0] : 'new project'}</div>
        </div>
      </header>

      <section className="hero-block">
        <div className="eyebrow"><Sparkles size={15} /> FROM IDEA TO CUT</div>
        <h1>Make the story<br /><em>watchable.</em></h1>
        <p>One guided workspace for research-driven scripts, narration, image direction, and the final film.</p>
      </section>

      <nav className="stepper" aria-label="Documentary workflow">
        {steps.map((step) => <button key={step.id} className={`${activeStep >= step.id ? 'active' : ''} ${activeStep === step.id ? 'current' : ''}`} onClick={() => activeStep >= step.id && setActiveStep(step.id)}><span>{activeStep > step.id ? <Check size={13} /> : step.id}</span>{step.label}</button>)}
      </nav>
      <div className="progress-track" aria-label={`Step ${activeStep} of ${steps.length}`}><span style={{ width: `${(activeStep / steps.length) * 100}%` }} /></div>

      <section className="workspace">
        <aside className="sidebar">
          <div className="sidebar-label">PROJECT NOTES</div>
          <div className="project-note"><span className="note-dot" />{topic || 'Untitled documentary'}</div>
          <div className="sidebar-rule" />
          <p>{message}</p>
          {session && <div className="session-id">SESSION<br /><strong>{session.session_id}</strong></div>}
        </aside>

        <div className="stage">
          {error && <div className="error-banner">{error}</div>}

          {activeStep === 1 && <section className="panel intro-panel">
            <div className="panel-kicker">01 / BEGIN WITH THE SUBJECT</div>
            <h2>What should we<br /><em>remember?</em></h2>
            <form onSubmit={createSession}>
              <label>Documentary topic<input autoFocus value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="The hidden engineering of the Taj Mahal" /></label>
              <label>Editorial lens<select value={genre} onChange={(e) => setGenre(e.target.value)}><option value="history">History</option><option value="nature">Nature</option><option value="biography">Biography</option><option value="science">Science</option><option value="culture">Culture</option><option value="technology">Technology</option><option value="architecture">Architecture</option><option value="archaeology">Archaeology</option><option value="investigative">Investigative</option><option value="human stories">Human stories</option><option value="food">Food and traditions</option><option value="arts">Arts and heritage</option><option value="environment">Environment</option></select></label>
              <label>Script language<select value={scriptLanguage} onChange={(e) => setScriptLanguage(e.target.value)}><option value="hindi">Hindi</option><option value="english">English</option><option value="hinglish">Hinglish</option><option value="bengali">Bengali</option><option value="tamil">Tamil</option><option value="telugu">Telugu</option><option value="marathi">Marathi</option><option value="gujarati">Gujarati</option><option value="kannada">Kannada</option><option value="malayalam">Malayalam</option><option value="punjabi">Punjabi</option></select></label>
              <label>Visual type<select value={visualStyle} onChange={(e) => setVisualStyle(e.target.value)}><option value="photorealistic">Photorealistic documentary</option><option value="cartoon">Cartoon animation</option><option value="anime">Anime illustration</option><option value="3d_animation">3D animation</option><option value="illustrated">Painted illustration</option><option value="archival">Archival film</option><option value="watercolor">Watercolor and ink</option><option value="graphic_novel">Graphic novel</option><option value="claymation">Clay animation</option><option value="noir">Documentary noir</option></select></label>
              <label>Target video seconds<input type="number" min="20" max="600" step="5" value={targetDuration} onChange={(e) => setTargetDuration(e.target.value)} /></label>
              <ActionButton type="submit" busy={busy === 'session'}>Open the story room <ArrowRight size={17} /></ActionButton>
            </form>
          </section>}

          {activeStep === 2 && <section className="panel">
            <PanelHeading icon={<FileText />} kicker="02 / SCRIPT" title="Find the thread." detail="A continuous spoken script, shaped around your subject and editorial lens." />
            {!script ? <ActionButton onClick={generateScript} busy={busy === 'script'}>Generate {scriptLanguage} script <WandSparkles size={17} /></ActionButton> : <><label className="edit-label">Edit {scriptLanguage} script<textarea className="large-text" value={script} onChange={(e) => { setScript(e.target.value); setScriptSaved(false); }} /></label>{scriptLanguage === 'hindi' && !hasDevanagari(script) && <div className="language-warning">This saved script is not Hindi. Regenerate it to replace the older draft.</div>}<div className="panel-actions"><ActionButton secondary onClick={() => setActiveStep(1)}><ArrowLeft size={15} /> Back to topic</ActionButton><div className="inline-actions"><ActionButton secondary onClick={generateScript} busy={busy === 'script'}><WandSparkles size={15} /> Regenerate {scriptLanguage}</ActionButton><ActionButton secondary onClick={saveScript} busy={busy === 'save-script'}><Save size={15} /> {scriptSaved ? 'Saved' : 'Save changes'}</ActionButton><a className="text-link" href={downloadUrl('documentary_script.txt')} download><Download size={15} /> Download script</a><ActionButton onClick={() => setActiveStep(3)}>Continue to narration <ArrowRight size={17} /></ActionButton></div></div></>}
          </section>}

          {activeStep === 3 && <section className="panel">
            <PanelHeading icon={<Mic2 />} kicker="03 / NARRATION" title="Give it a voice." detail="Choose a voice, preview the narration, and let the pace set the edit." />
            <label>Voice character<select value={voice} onChange={(e) => setVoice(e.target.value)}><option>Iapetus</option><option>Kore</option><option>Zephyr</option><option>Nova</option></select></label>
            <ActionButton onClick={generateAudio} busy={busy === 'audio'}>Generate narration <Play size={17} /></ActionButton>
            {audioUrl && <><div className="media-strip"><audio controls src={audioUrl} /><a className="text-link" href={audioUrl} download><Download size={15} /> Download WAV</a></div><div className="panel-actions"><ActionButton secondary onClick={() => setActiveStep(2)}><ArrowLeft size={15} /> Back to script</ActionButton><ActionButton onClick={() => setActiveStep(4)}>Continue to image prompts <ArrowRight size={17} /></ActionButton></div></>}
          </section>}

          {activeStep === 4 && <section className="panel">
            <PanelHeading icon={<WandSparkles />} kicker="04 / VISUAL DIRECTION" title="Describe what we see." detail="Create the numbered image prompts and the production brief for consistent generation." />
            {!prompts.length ? <ActionButton onClick={generatePrompts} busy={busy === 'prompts'}>Generate image prompts <Sparkles size={17} /></ActionButton> : <PromptReview prompts={prompts} generationPrompts={generationPrompts} downloadUrl={downloadUrl} onBack={() => setActiveStep(3)} onContinue={() => setActiveStep(5)} />}
          </section>}

          {activeStep === 5 && <section className="panel">
            <PanelHeading icon={<FileImage />} kicker="05 / IMAGE BAY" title="Bring the frames." detail={`Upload ${prompts.length || 'your'} numbered images. The system will organize them against the prompt sequence.`} />
            <label className="drop-zone"><Upload size={24} /><strong>{files.length ? `${files.length} images selected` : 'Choose image files'}</strong><span>JPEG, PNG, or WEBP · name them 1.jpeg, 2.jpeg, 3.jpeg…</span><input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(e) => setFiles(Array.from(e.target.files || []))} /></label>
            <ActionButton onClick={uploadImages} busy={busy === 'upload'} disabled={!files.length}>Upload and organize <ArrowRight size={17} /></ActionButton>
            {uploadSummary && <div className={`upload-summary ${uploadSummary.missing.length ? 'incomplete' : ''}`}>
              <strong>{uploadSummary.uploaded} / {uploadSummary.required} images accepted</strong>
              {uploadSummary.missing.length > 0 && <span>Missing: {uploadSummary.missing.join(', ')}</span>}
            </div>}
            {uploadResults.length > 0 && <div className="upload-list">{uploadResults.map((item) => <div key={`${item.name}-${item.target}`}><Check size={15} /> {item.name} <span>{item.target || item.reason}</span></div>)}</div>}
            <div className="panel-actions"><ActionButton secondary onClick={() => setActiveStep(4)}><ArrowLeft size={15} /> Back to prompts</ActionButton></div>
          </section>}

          {activeStep === 6 && <section className="panel finish-panel">
            <PanelHeading icon={<Film />} kicker="06 / FINAL CUT" title="Roll the film." detail="Set the pacing and audio mix, then render the documentary." />
            <div className="render-settings">
              <label>Seconds per image<input type="number" min="1" max="30" step="0.5" value={imageSeconds} onChange={(e) => setImageSeconds(e.target.value)} /></label>
              <label>Transition seconds<input type="number" min="0" max="10" step="0.1" value={transitionSeconds} onChange={(e) => setTransitionSeconds(e.target.value)} /></label>
              <label>Narration volume<input type="number" min="0" max="3" step="0.1" value={narrationVolume} onChange={(e) => setNarrationVolume(e.target.value)} /></label>
              <label>BGM volume<input type="number" min="0" max="1" step="0.05" value={bgmVolume} onChange={(e) => setBgmVolume(e.target.value)} /></label>
            </div>
            <div className="panel-actions"><ActionButton secondary onClick={() => setActiveStep(5)}><ArrowLeft size={15} /> Back to images</ActionButton><ActionButton onClick={buildVideo} busy={busy === 'video'}>Assemble documentary <Film size={17} /></ActionButton></div>
            {currentVideo && <div className="video-wrap"><video controls src={currentVideo} /><div className="video-meta"><span><span className="live-dot" /> FINAL CUT READY</span>{musicTrack && <span>BGM · {musicTrack}</span>}<a className="text-link" href={currentVideo} download><Download size={15} /> Download MP4</a></div></div>}
            {currentVideo && <ArtifactDownloads downloadUrl={downloadUrl} folder={session?.folder} />}
            {videoUrl && !finalVideoUrl && <p className="muted">Final music mix is being prepared…</p>}
          </section>}
        </div>
      </section>
    </main>
  );
}

function PanelHeading({ icon, kicker, title, detail }) {
  return <div className="panel-heading"><div className="panel-icon">{icon}</div><div><div className="panel-kicker">{kicker}</div><h2>{title}</h2><p>{detail}</p></div></div>;
}

function PromptReview({ prompts, generationPrompts, downloadUrl, onBack, onContinue }) {
  const [tab, setTab] = useState('scenes');
  return <>
    <div className="prompt-tabs"><button className={tab === 'scenes' ? 'selected' : ''} onClick={() => setTab('scenes')}>Scene prompts <span>{prompts.length}</span></button><button className={tab === 'guide' ? 'selected' : ''} onClick={() => setTab('guide')}>Generation guide</button></div>
    {tab === 'scenes' ? <div className="prompt-list">{prompts.map((prompt, index) => <article key={prompt}><span>{String(index + 1).padStart(2, '0')}</span><p>{prompt.replace(/^\d+\.\s*/, '')}</p></article>)}</div> : <textarea className="large-text guide-text" value={generationPrompts} readOnly />}
    <div className="panel-actions"><ActionButton secondary onClick={onBack}><ArrowLeft size={15} /> Back to narration</ActionButton><div className="inline-actions"><a className="text-link" href={downloadUrl(tab === 'scenes' ? 'image_prompts.txt' : 'image_generation_prompts.txt')} download><Download size={15} /> Download {tab === 'scenes' ? 'scenes' : 'guide'}</a><ActionButton onClick={onContinue}>Move to image bay <ArrowRight size={17} /></ActionButton></div></div>
  </>;
}

function ArtifactDownloads({ downloadUrl, folder }) {
  const artifacts = [
    ['documentary_script.txt', 'Hindi script'],
    ['narration.wav', 'Narration WAV'],
    ['image_prompts.txt', 'Image prompts'],
    ['image_generation_prompts.txt', 'Generation guide'],
    ['documentary_video.mp4', 'Video without BGM'],
    ['documentary_final_with_music.mp4', 'Final video with BGM'],
  ];
  return <section className="artifact-box">
    <div className="panel-kicker">PROJECT ARTIFACTS</div>
    {folder && <p className="artifact-folder">Saved in: {folder}</p>}
    <div className="artifact-list">{artifacts.map(([filename, label]) => <a key={filename} className="text-link" href={downloadUrl(filename)} download><Download size={15} /> {label}</a>)}</div>
  </section>;
}

export default App;
