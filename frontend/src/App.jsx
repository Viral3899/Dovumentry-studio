import { useEffect, useRef, useState } from 'react';
import {
  ArrowLeft, ArrowRight, Check, Clapperboard, Copy, Download,
  FileImage, FileText, Film, Hash, Share2, LoaderCircle, LogOut,
  Mic2, Moon, Play, Save, Sparkles, Sun, Upload, WandSparkles, Video, ExternalLink, BookOpen, Archive, Lock, AlertTriangle,
} from 'lucide-react';

const steps = [
  { id: 0, label: 'Discover' },
  { id: 1, label: 'Topic' },
  { id: 2, label: 'Script' },
  { id: 3, label: 'Narration' },
  { id: 4, label: 'Prompts' },
  { id: 5, label: 'Image Bay' },
  { id: 6, label: 'Video' },
];

function canAccessStep(stepId, state) {
  if (stepId === 0) return true;
  if (stepId === 1) return true;
  if (stepId === 2) return !!state.topic;
  if (stepId === 3) return !!state.script;
  if (stepId === 4) return !!state.audioUrl;
  if (stepId === 5) return !!state.prompts?.length;
  if (stepId === 6) return !!state.uploadResults?.length;
  return false;
}

function getStepBlocker(stepId) {
  if (stepId === 2) return 'Enter a topic first';
  if (stepId === 3) return 'Generate or write a script first';
  if (stepId === 4) return 'Generate narration first';
  if (stepId === 5) return 'Generate image prompts first';
  if (stepId === 6) return 'Upload images first';
  return null;
}

async function requestJson(url, options = {}) {
  const response = await fetch(url, { ...options, credentials: 'include' });
  const result = await response.json().catch(() => ({}));
  if (!response.ok || !result.success) {
    if (result.provider_required) window.dispatchEvent(new CustomEvent('provider-required', { detail: result }));
    const error = new Error(result.message || 'Something went wrong.');
    error.providerRequired = Boolean(result.provider_required);
    error.provider = result.provider;
    throw error;
  }
  return result;
}

function ApiKeyModal({ request, onClose, onSaved, onUseDefaultVoice }) {
  const [provider, setProvider] = useState(request?.provider || 'groq');
  const [apiKey, setApiKey] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setProvider(request?.provider || 'groq'); setApiKey(''); setError(''); }, [request]);
  if (!request) return null;
  const save = async () => {
    if (!apiKey.trim()) { setError('Enter the API key first.'); return; }
    setBusy(true); setError('');
    try {
      await requestJson('/api/providers/key', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ provider, api_key:apiKey.trim() }) });
      setApiKey('');
      onClose();
      if (onSaved) onSaved(provider);
    } catch (err) { setError(err.message); } finally { setBusy(false); }
  };
  const primary = provider === 'groq';
  return <div className="api-key-overlay" role="dialog" aria-modal="true">
    <div className="api-key-modal">
      <div className="panel-kicker">AI PROVIDER REQUIRED</div>
      <h2>{primary ? 'Groq API key required' : 'Gemini API key required'}</h2>
      <p>{request.message}</p>
      <div className="api-key-provider-row">
        <button className={provider==='groq'?'selected':''} onClick={()=>setProvider('groq')}>Groq <span>Primary</span></button>
        <button className={provider==='gemini'?'selected':''} onClick={()=>setProvider('gemini')}>Gemini <span>Alternate</span></button>
      </div>
      <label>{provider.toUpperCase()} API KEY<input autoFocus type="password" value={apiKey} onChange={e=>setApiKey(e.target.value)} placeholder={provider==='groq'?'gsk_…':'AIza…'} onKeyDown={e=>e.key==='Enter'&&save()} /></label>
      {error && <div className="error-banner">{error}</div>}
      <div className="api-key-note"><strong>Saved for future use.</strong><span>The key is stored locally in this studio and reused on later steps and app restarts.</span></div>
      <div className="panel-actions">
        <ActionButton secondary onClick={onClose}>Cancel</ActionButton>
        {request.allow_default_voice && provider === 'gemini' && <ActionButton secondary onClick={() => { onClose(); onUseDefaultVoice?.(); }}>Use Default Voice</ActionButton>}
        <ActionButton onClick={save} busy={busy}>Save API key</ActionButton>
      </div>
    </div>
  </div>;
}

function SkipToStepModal({ targetStep, blocker, onClose, onConfirm }) {
  const [audioFile, setAudioFile] = useState(null);
  const [imageFiles, setImageFiles] = useState([]);
  const [settings, setSettings] = useState({
    transitionSeconds: 1,
    narrationVolume: 1.5,
    bgmVolume: 0.2,
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const stepLabels = ['Discover', 'Topic', 'Script', 'Narration', 'Prompts', 'Image Bay', 'Final Cut'];

  const handleConfirm = async () => {
    setBusy(true);
    setError('');
    try {
      await onConfirm({ audioFile, imageFiles, settings });
      onClose();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const needsAudio = targetStep >= 3;
  const needsImages = targetStep >= 5;
  const needsSettings = targetStep >= 6;

  if (!targetStep) return null;

  return (
    <div className="skip-modal-overlay" role="dialog" aria-modal="true">
      <div className="skip-modal">
        <div className="panel-kicker">SKIP TO {stepLabels[targetStep].toUpperCase()}</div>
        <h2>Jump directly to <em>{stepLabels[targetStep]}</em>?</h2>
        <p className="skip-modal-note">This step requires: {blocker}. Provide the missing inputs below to continue.</p>

        {needsAudio && (
          <div className="skip-field-group">
            <label className="skip-field-label">
              <Mic2 size={14} /> Narration Audio (WAV/MP3)
              <input type="file" accept=".wav,.mp3,.m4a" onChange={(e) => setAudioFile(e.target.files?.[0] || null)} />
              {audioFile && <span className="file-selected">{audioFile.name}</span>}
            </label>
          </div>
        )}

        {needsImages && (
          <div className="skip-field-group">
            <label className="skip-field-label">
              <FileImage size={14} /> Images (JPEG/PNG/WebP) — select all numbered images
              <input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(e) => setImageFiles(Array.from(e.target.files || []))} />
              {imageFiles.length > 0 && <span className="file-selected">{imageFiles.length} images selected</span>}
            </label>
          </div>
        )}

        {needsSettings && (
          <div className="skip-field-group">
            <label className="skip-field-label"><Film size={14} /> Final Cut Settings</label>
            <div className="skip-settings-grid">
              <label>Transition seconds<input type="number" min="0" max="10" step="0.1" value={settings.transitionSeconds} onChange={(e) => setSettings({...settings, transitionSeconds: parseFloat(e.target.value)})} /></label>
              <label>Narration volume<input type="number" min="0" max="3" step="0.1" value={settings.narrationVolume} onChange={(e) => setSettings({...settings, narrationVolume: parseFloat(e.target.value)})} /></label>
              <label>BGM volume<input type="number" min="0" max="1" step="0.05" value={settings.bgmVolume} onChange={(e) => setSettings({...settings, bgmVolume: parseFloat(e.target.value)})} /></label>
            </div>
          </div>
        )}

        {error && <div className="error-banner">{error}</div>}

        <div className="panel-actions">
          <ActionButton secondary onClick={onClose}>Cancel</ActionButton>
          <ActionButton onClick={handleConfirm} busy={busy} disabled={needsAudio && !audioFile || needsImages && imageFiles.length === 0}>
            Confirm & Skip <ArrowRight size={17} />
          </ActionButton>
        </div>
      </div>
    </div>
  );
}

function ActionButton({ children, busy, onClick, disabled, secondary = false, danger = false, type = 'button' }) {
  return (
    <button
      className={`action-button${secondary ? ' secondary' : ''}${danger ? ' danger' : ''}`}
      type={type}
      onClick={onClick}
      disabled={disabled || busy}
    >
      {busy ? <LoaderCircle className="spin" size={17} /> : children}
    </button>
  );
}

function CopyButton({ text }) {
  const [copied, setCopied] = useState(false);
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(text || '');
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  };
  return (
    <button className="copy-btn" onClick={copy} title="Copy to clipboard">
      {copied ? <Check size={13} /> : <Copy size={13} />}
      {copied ? 'Copied' : 'Copy'}
    </button>
  );
}

function hasDevanagari(text) {
  return /[\u0900-\u097F]/.test(text || '');
}

function getInitialTheme() {
  const saved = localStorage.getItem('documentary-theme');
  return saved === 'light' || saved === 'dark' ? saved : 'dark';
}

/* ─── Login ──────────────────────────────────────────────── */
function LoginScreen({ onLogin, googleConfigured }) {
  const [role, setRole] = useState('admin');
  const [identifier, setIdentifier] = useState('demo');
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
        body: JSON.stringify({ identifier, password, role }),
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
      const result = await requestJson('/api/auth/google', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ credential: response.credential }),
      });
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
      window.google.accounts.id.renderButton(document.getElementById('google-sign-in'), {
        theme: 'outline', size: 'large', width: 360, text: 'signin_with',
      });
    };
    renderGoogleButton();
    return undefined;
  }, [googleConfigured, authView]);

  if (authView === 'home') return (
    <main className="auth-shell">
      <section className="panel auth-panel auth-home-panel">
        <div className="brand-mark"><Clapperboard size={20} /> DOCUMENTARY STUDIO</div>
        <div className="panel-kicker">A WORKSPACE FOR STORIES</div>
        <h1>Make the story<br /><em>watchable.</em></h1>
        <p className="auth-copy">Research-driven scripts, narration, visuals, and finished documentaries — in one focused studio.</p>
        <div className="auth-home-actions">
          <ActionButton onClick={() => setAuthView('login')}>Log in <ArrowRight size={17} /></ActionButton>
          <ActionButton secondary onClick={() => setAuthView('signup')}>Sign up <Sparkles size={17} /></ActionButton>
        </div>
      </section>
    </main>
  );

  return (
    <main className="auth-shell">
      <section className="panel auth-panel">
        <div className="brand-mark"><Clapperboard size={20} /> DOCUMENTARY STUDIO</div>
        <div className="panel-kicker">{authView === 'login' ? 'STUDIO ACCESS' : 'CREATE YOUR ACCOUNT'}</div>
        <h1>{authView === 'login' ? <>Enter the<br /><em>story room.</em></> : <>Join the<br /><em>story room.</em></>}</h1>
        <p className="auth-copy">
          {authView === 'login'
            ? 'Sign in to create, edit, and render documentaries.'
            : 'Use your approved Google account to join this documentary studio.'}
        </p>
        {error && <div className="error-banner">{error}</div>}
        {authView === 'login' ? (
          <form onSubmit={submit}>
            <div className="role-switch" role="group" aria-label="Account type">
              <button type="button" className={role === 'admin' ? 'selected' : ''} onClick={() => setRole('admin')}>Admin</button>
              <button type="button" className={role === 'user' ? 'selected' : ''} onClick={() => setRole('user')}>User</button>
            </div>
            <label>Username, email, or phone<input autoFocus value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoComplete="username" /></label>
            <label>{role === 'admin' ? 'Admin' : 'User'} password<input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" /></label>
            <ActionButton type="submit" busy={busy} disabled={!identifier || !password}>Enter studio <ArrowRight size={17} /></ActionButton>
          </form>
        ) : (
          <div className="signup-note">
            <strong>One studio, approved accounts.</strong>
            <span>Signup is available for the Google email configured by the studio administrator.</span>
          </div>
        )}
        {googleConfigured && (
          <>
            <div className="auth-divider"><span>{authView === 'login' ? 'or continue with Google' : 'continue with Google'}</span></div>
            <div id="google-sign-in" className="google-sign-in" />
          </>
        )}
        <button className="auth-back-button" type="button" onClick={() => setAuthView(authView === 'login' ? 'home' : 'login')}>
          {authView === 'login' ? 'Back to home' : 'Already have an account? Log in'}
        </button>
      </section>
    </main>
  );
}

/* ─── Topic Discovery (Step 0) ───────────────────────────── */
function TopicDiscovery({ onSelectTopic, onSkip }) {
  const [seed, setSeed] = useState('');
  const [genre, setGenre] = useState('history');
  const [language, setLanguage] = useState('hindi');
  const [topics, setTopics] = useState([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [selected, setSelected] = useState(null);

  const suggest = async () => {
    if (!seed.trim()) { setError('Enter a seed idea first.'); return; }
    setBusy(true);
    setError('');
    try {
      const result = await requestJson('/api/suggest-topics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ seed, genre, language }),
      });
      setTopics(result.topics || []);
      setSelected(null);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const choose = (t) => {
    setSelected(t);
  };

  const confirm = () => {
    if (selected) onSelectTopic(selected.topic, genre, language);
  };

  return (
    <section className="panel discover-panel">
      <div className="panel-kicker">00 / FIND YOUR STORY</div>
      <h2>What should the<br /><em>world know?</em></h2>
      <p className="discover-sub">Drop a rough idea or niche below. We'll generate 5 specific, researchable documentary topics with opening hooks.</p>

      <div className="discover-form">
        <label>
          Seed idea or niche
          <input
            autoFocus
            value={seed}
            onChange={(e) => setSeed(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && suggest()}
            placeholder="e.g. forgotten Indian emperors, ocean microplastics, ancient trade routes"
          />
        </label>
        <div className="discover-row">
          <label>
            Genre
            <select value={genre} onChange={(e) => setGenre(e.target.value)}>
              <option value="history">History</option>
              <option value="nature">Nature</option>
              <option value="biography">Biography</option>
              <option value="science">Science</option>
              <option value="culture">Culture</option>
              <option value="technology">Technology</option>
              <option value="architecture">Architecture</option>
              <option value="archaeology">Archaeology</option>
              <option value="investigative">Investigative</option>
              <option value="human stories">Human stories</option>
              <option value="food">Food and traditions</option>
              <option value="environment">Environment</option>
            </select>
          </label>
          <label>
            Output language
            <select value={language} onChange={(e) => setLanguage(e.target.value)}>
              <option value="english">English</option>
              <option value="hindi">Hindi</option>
              <option value="hinglish">Hinglish</option>
              <option value="bengali">Bengali</option>
              <option value="tamil">Tamil</option>
              <option value="telugu">Telugu</option>
              <option value="marathi">Marathi</option>
              <option value="gujarati">Gujarati</option>
              <option value="kannada">Kannada</option>
              <option value="malayalam">Malayalam</option>
              <option value="punjabi">Punjabi</option>
            </select>
          </label>
        </div>
        {error && <div className="error-banner">{error}</div>}
        <ActionButton onClick={suggest} busy={busy}>
          <Sparkles size={16} /> Generate topic ideas
        </ActionButton>
      </div>

      {topics.length > 0 && (
        <div className="topic-cards">
          <div className="topic-cards-label">PICK ONE TO DEVELOP →</div>
          {topics.map((t, i) => (
            <article
              key={i}
              className={`topic-card${selected === t ? ' selected' : ''}`}
              onClick={() => choose(t)}
            >
              <div className="topic-card-num">{String(i + 1).padStart(2, '0')}</div>
              <div className="topic-card-body">
                <h3>{t.topic}</h3>
                <p className="topic-hook">"{t.hook}"</p>
                <div className="topic-meta-row">
                  <span className="topic-angle-chip">{t.angle}</span>
                  <span className="topic-why">{t.why}</span>
                </div>
                {t.keywords?.length > 0 && (
                  <div className="topic-keywords">
                    {t.keywords.map((k) => <span key={k}><Hash size={11} />{k}</span>)}
                  </div>
                )}
              </div>
              {selected === t && <div className="topic-card-check"><Check size={16} /></div>}
            </article>
          ))}
          <div className="discover-actions">
            <ActionButton secondary onClick={suggest} busy={busy}>
              <Sparkles size={15} /> Regenerate ideas
            </ActionButton>
            <ActionButton onClick={confirm} disabled={!selected}>
              Develop this topic <ArrowRight size={17} />
            </ActionButton>
          </div>
        </div>
      )}

      <div className="discover-skip">
        <button className="skip-link" onClick={onSkip}>
          I already have a topic — skip this step <ArrowRight size={13} />
        </button>
      </div>
    </section>
  );
}

/* ─── Social Media Panel ─────────────────────────────────── */
function SocialMediaPanel({ sessionId }) {
  const [social, setSocial] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [activeTab, setActiveTab] = useState('youtube');
  const [language, setLanguage] = useState('en');

  const generate = async () => {
    if (!sessionId) {
      setError('Your documentary session is not ready yet.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      const result = await requestJson('/api/generate-social', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ session_id: sessionId, language }),
      });
      setSocial(result);
    } catch (err) {
      setError(err.message || 'Social copy generation failed.');
    } finally {
      setBusy(false);
    }
  };

  useEffect(() => {
    if (sessionId) generate();
    // Generate once when the final-cut panel mounts. The button remains available for regeneration.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId]);

  return (
    <section className="social-panel">
      <div className="panel-kicker">PUBLISH YOUR DOCUMENTARY</div>
      <h3>Ready to share?<br /><em>Get your copy.</em></h3>
      <p className="social-sub">Generate everything you need to publish: YouTube title + description, Instagram caption, SEO tags, and a finished thumbnail with the text baked directly into the image.</p>

      <div className="social-language-row">
        <label>CONTENT LANGUAGE
          <select value={language} onChange={(e) => { setLanguage(e.target.value); setSocial(null); }}>
            <option value="en">English</option>
            <option value="hi">हिन्दी (Hindi)</option>
          </select>
        </label>
        <span>Hindi thumbnail text uses a Devanagari-compatible font.</span>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {!social ? (
        <ActionButton onClick={generate} busy={busy}>
          <Sparkles size={16} /> {busy ? 'Generating social copy…' : 'Generate social copy'}
        </ActionButton>
      ) : (
        <>
          <div className="social-tabs">
            <button className={activeTab === 'youtube' ? 'selected' : ''} onClick={() => setActiveTab('youtube')}>
              <Video size={14} /> YouTube
            </button>
            <button className={activeTab === 'instagram' ? 'selected' : ''} onClick={() => setActiveTab('instagram')}>
              <Share2 size={14} /> Instagram
            </button>
            <button className={activeTab === 'tags' ? 'selected' : ''} onClick={() => setActiveTab('tags')}>
              <Hash size={14} /> Tags
            </button>
            <button className={activeTab === 'thumbnail' ? 'selected' : ''} onClick={() => setActiveTab('thumbnail')}>
              <FileImage size={14} /> Thumbnail
            </button>
          </div>

          {activeTab === 'youtube' && (
            <div className="social-block">
              <div className="social-field">
                <div className="social-field-label">VIDEO TITLE <CopyButton text={social.youtube_title} /></div>
                <p className="social-title-preview">{social.youtube_title}</p>
                <span className="social-char-count">{social.youtube_title.length} / 70 characters</span>
              </div>
              <div className="social-field">
                <div className="social-field-label">DESCRIPTION <CopyButton text={social.youtube_description} /></div>
                <textarea className="social-textarea" value={social.youtube_description} readOnly aria-label="YouTube description" />
                <span className="social-char-count">{social.youtube_description.length} characters · Ready to paste into YouTube</span>
              </div>
            </div>
          )}

          {activeTab === 'instagram' && (
            <div className="social-block">
              <div className="social-field">
                <div className="social-field-label">CAPTION <CopyButton text={social.instagram_caption} /></div>
                <textarea className="social-textarea tall" value={social.instagram_caption} readOnly aria-label="Instagram caption" />
                <span className="social-char-count">{social.instagram_caption.length} / 2200 characters</span>
              </div>
            </div>
          )}

          {activeTab === 'tags' && (
            <div className="social-block">
              <div className="social-field">
                <div className="social-field-label">YOUTUBE TAGS <CopyButton text={(social.tags || []).join(', ')} /></div>
                <div className="tags-grid">
                  {(social.tags || []).map((tag) => <span key={tag} className="tag-chip">{tag}</span>)}
                </div>
              </div>
            </div>
          )}

          {activeTab === 'thumbnail' && (
            <div className="social-block">
              {social.thumbnail_image_url && (
                <div className="social-field">
                  <div className="social-field-label">FINISHED THUMBNAIL <a className="copy-btn" href={social.thumbnail_image_url} download="thumbnail.png">Download PNG</a></div>
                  <div className="thumbnail-image-frame">
                    <img src={social.thumbnail_image_url} alt="Generated documentary thumbnail with text overlay" />
                  </div>
                  <p className="social-char-count">1280 × 720 · Text is baked into the image</p>
                </div>
              )}
              {social.thumbnail_text && (social.thumbnail_text.main_title || social.thumbnail_text.subtitle) && (
                <div className="social-field">
                  <div className="social-field-label">TEXT OVERLAY</div>
                  <div className="thumbnail-text-preview">
                    {social.thumbnail_text.label && (
                      <span className="thumb-label">{social.thumbnail_text.label}</span>
                    )}
                    <div className="thumb-main-title">{social.thumbnail_text.main_title}</div>
                    {social.thumbnail_text.subtitle && (
                      <div className="thumb-subtitle">{social.thumbnail_text.subtitle}</div>
                    )}
                  </div>
                  <CopyButton text={[social.thumbnail_text.main_title, social.thumbnail_text.subtitle, social.thumbnail_text.label].filter(Boolean).join(' · ')} />
                </div>
              )}
              <div className="social-field">
                <div className="social-field-label">IMAGE PROMPT <CopyButton text={social.thumbnail_prompt || ''} /></div>
                <div className="thumbnail-prompt-box">
                  <p>{social.thumbnail_prompt || 'No thumbnail prompt generated.'}</p>
                </div>
                <p className="social-char-count thumbnail-hint">
                  The finished PNG above already contains the text overlay. The prompt is available if you want to create a different background in Midjourney / DALL·E.
                </p>
              </div>
            </div>
          )}

          <div className="social-regen">
            <ActionButton secondary onClick={generate} busy={busy}>
              <Sparkles size={14} /> Regenerate copy
            </ActionButton>
          </div>
        </>
      )}
    </section>
  );
}

/* ─── Reusable components ────────────────────────────────── */
function PanelHeading({ icon, kicker, title, detail }) {
  return (
    <div className="panel-heading">
      <div className="panel-icon">{icon}</div>
      <div>
        <div className="panel-kicker">{kicker}</div>
        <h2>{title}</h2>
        <p>{detail}</p>
      </div>
    </div>
  );
}


function FlowGuide({ prompts, generationPrompts, downloadUrl }) {
  const count = prompts.length || 0;
  const batchCount = count > 0 ? 1 : 0;
  const agentInstruction = `Generate a text-to-image prompt for each topic using: [Subject/Scene] + [Time period/setting] + [Visual style] + [Lighting] + [Camera angle] + [Mood/atmosphere].\n\nKeep the visual style, characters, locations, period details, wardrobe, architecture, materials, color language, and cinematic documentary continuity consistent across the project. Use 16:9 landscape. No text, captions, logos, subtitles, or watermarks.\n\nGenerate only the requested numbered batch. Generate all images required by the batch; do not force a fixed batch size. After the batch is fully generated, continue with the next numbered batch only if more images remain.`;
  const steps = [
    { n: 1, title: 'Open Google Flow', image: '/flow-guide/01-open-google-flow.png', file: '01-open-flow.txt', text: 'Open Flow → New project → enter the project → open the Agent/project controls.' },
    { n: 2, title: 'Open Agent Instructions', image: '/flow-guide/02-open-agent-instructions.png', file: '02-agent-instructions.txt', text: 'Open Agent instructions, paste the exact instruction below, and keep it enabled.' },
    { n: 3, title: 'Model, 16:9 & Output Settings', image: '/flow-guide/03-set-image-defaults.png', file: '03-image-settings.txt', text: 'Open the model/settings menu. Select the image model available in Flow, set 16:9 landscape, set Outputs to 1, choose Never for confirmation before generating, and keep Outputs at 1 for every generation.' },
    { n: 4, title: 'Generate Current Batch', image: '/flow-guide/04-paste-batch-prompt.png', file: '04-batch-generation.txt', text: 'Paste the current numbered batch into Flow and generate all images required for the current batch; do not force a fixed batch size. Wait until every image in that batch is finished.' },
    { n: 5, title: 'Continue Next Batch', image: '/flow-guide/05-continue-every-batch.png', file: '05-next-batch.txt', text: 'After the first batch is completely generated, paste the next numbered batch only if more images remain, continuing the numbering from the previous batch until the required image count is complete.' },
    { n: 6, title: 'Rename FIRST → Refresh → Download Project', image: '/flow-guide/06-rename-download-upload.png', file: '06-rename-download-upload.txt', text: 'After ALL images finish: run the supplied rename command FIRST (1.jpeg, 2.jpeg, 3.jpeg…), then REFRESH Flow, then open the THREE-DOTS menu and choose Download Project. Only after the download finishes, continue to Image Bay.' },
  ];

  return (
    <div className="flow-guide">
      <div className="flow-guide-head">
        <div>
          <div className="social-field-label"><BookOpen size={14} /> GOOGLE FLOW IMAGE GENERATION GUIDE</div>
          <h3>Generate the frames in Flow.</h3>
          <p>Each instruction is now a separate step with its own visual and downloadable guide file. Follow them in order from opening Flow to Image Bay.</p>
        </div>
        <a className="action-button flow-open" href="https://labs.google/fx/tools/flow" target="_blank" rel="noreferrer">Open Google Flow <ExternalLink size={16} /></a>
      </div>

      <div className="flow-visual-map" aria-label="Google Flow image generation workflow">
        <div className="flow-visual-intro"><div className="flow-visual-icon">✦</div><div><strong>Six-step visual workflow</strong><span>New Project → Agent → Instruction → Model/16:9/Outputs 1/Never → Generate Batch → Next Batch if needed → Rename FIRST → Refresh → Three dots → Download Project</span></div></div>
        <div className="flow-visual-track">
          {steps.map((step, i) => <div className="flow-track-group" key={step.n}><div className={`flow-visual-node ${i === 0 ? 'active' : ''}`}><span>{String(step.n).padStart(2, '0')}</span><strong>{step.title}</strong><small>{i === 2 ? '16:9 · Outputs 1 · Never' : i === 3 ? 'Generate required images' : i === 4 ? 'Repeat only if needed' : i === 5 ? 'Three dots → Download' : 'Follow this step'}</small></div>{i < steps.length - 1 && <i aria-hidden="true">→</i>}</div>)}
        </div>
      </div>

      <div className="flow-step-files">
        {steps.map((step) => (
          <article className="flow-step-file" key={step.n}>
            <div className="flow-step-file-visual"><img src={step.image} alt={`Google Flow step ${step.n}: ${step.title}`} /></div>
            <div className="flow-step-file-copy">
              <div className="flow-step-file-number">STEP {String(step.n).padStart(2, '0')}</div>
              <h4>{step.title}</h4>
              <p>{step.text}</p>
              <div className="flow-step-file-actions">
                <a className="text-link" href={step.image} target="_blank" rel="noreferrer"><FileImage size={15} /> Open visual</a>
                <a className="text-link" href={downloadUrl(step.file)} download><Download size={15} /> Download step</a>
              </div>
            </div>
          </article>
        ))}
      </div>

      <div className="flow-rule-cards">
                        <div className="flow-rule-card"><span className="flow-rule-number">1→N</span><div><strong>Continuous numbering</strong><small>Batch 1 starts at 1; if another batch is needed, continue from the next number.</small></div></div>
      </div>

      <div className="flow-agent-box">
        <div className="social-field-label">AGENT INSTRUCTION <CopyButton text={agentInstruction} /></div>
        <textarea className="large-text flow-instruction" value={agentInstruction} readOnly />
      </div>

      <div className="flow-batches">
        <div className="social-field-label">BATCH PLAN · REQUIRED IMAGES</div>
        {Array.from({ length: batchCount }, (_, i) => {
          const start = i * (count || 1) + 1;
          const end = Math.min((i + 1) * (count || 1), count || 1);
          const batchPrompts = (prompts || []).slice(start - 1, end);
          const text = batchPrompts.length ? `Generate only prompts ${start}–${end} in this batch.\n\n${batchPrompts.map((prompt, j) => `${start + j}. ${prompt}`).join('\n\n')}` : `Generate prompts ${start}–${end} in this batch.`;
          return <div className="flow-batch" key={i}><div><strong>Batch {i + 1}</strong><span>Images {start}–{end}</span></div><CopyButton text={text} /></div>;
        })}
      </div>

      <div className="flow-final-note"><Archive size={18} /><div><strong>After ALL images are generated</strong><span>Run the rename command, refresh Flow, open the <strong>three-dots menu</strong>, choose <strong>Download project</strong>, extract the image files if needed, then return to Image Bay and upload them.</span></div></div>
      <div className="flow-guide-actions"><a className="text-link" href={downloadUrl('image_generation_prompts.txt')} download><Download size={15} /> Download full generation guide</a></div>
    </div>
  );
}

function PromptReview({ prompts, generationPrompts, downloadUrl, onBack, onContinue }) {
  const [tab, setTab] = useState('scenes');
  return (
    <>
      <div className="prompt-tabs">
        <button className={tab === 'scenes' ? 'selected' : ''} onClick={() => setTab('scenes')}>
          Scene prompts <span>{prompts.length}</span>
        </button>
        <button className={tab === 'guide' ? 'selected' : ''} onClick={() => setTab('guide')}>
          Generation guide
        </button>
      </div>
      {tab === 'scenes' ? (
        <div className="prompt-list">
          {prompts.map((prompt, index) => (
            <article key={prompt}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <p>{prompt.replace(/^\d+\.\s*/, '')}</p>
            </article>
          ))}
        </div>
      ) : (
        <textarea className="large-text guide-text" value={generationPrompts} readOnly />
      )}

      <div className="rename-before-refresh-card">
        <div className="social-field-label"><Archive size={14} /> RENAME BEFORE REFRESH — IMPORTANT</div>
        <p>After ALL Flow images are generated, rename the existing image files in their current order as <strong>1, 2, 3, 4, 5…</strong> while keeping their original extensions. <strong>ONLY rename the existing files.</strong> Do not generate, edit, replace, modify, or create any images. Then <strong>REFRESH Flow</strong>, open the <strong>three-dots menu → Download Project</strong>, and continue to Image Bay.</p>
        <div className="rename-command-box">
          <code>Rename existing image files sequentially as 1, 2, 3, 4, 5, ... in their current order. Keep extensions. ABSOLUTELY DO NOT generate, edit, modify, replace, or create any images. ONLY rename the existing files.</code>
          <CopyButton text={'Rename existing image files sequentially as 1, 2, 3, 4, 5, ... in their current order. Keep extensions. ABSOLUTELY DO NOT generate, edit, modify, replace, or create any images. ONLY rename the existing files.'} />
        </div>
      </div>

      <div className="panel-actions">
        <ActionButton secondary onClick={onBack}><ArrowLeft size={15} /> Back to narration</ActionButton>
        <div className="inline-actions">
          <a className="text-link" href={downloadUrl(tab === 'scenes' ? 'image_prompts.txt' : 'image_generation_prompts.txt')} download>
            <Download size={15} /> Download {tab === 'scenes' ? 'scenes' : 'guide'}
          </a>
          <ActionButton onClick={onContinue}>Go to Image Bay <ArrowRight size={17} /></ActionButton>
        </div>
      </div>
    </>
  );
}

function ArtifactDownloads({ downloadUrl, folder, videoFilename }) {
  const artifacts = [
    ['documentary_script.txt', 'Narration script'],
    ['narration.wav', 'Narration WAV'],
    ['image_prompts.txt', 'Image prompts'],
    ['image_generation_prompts.txt', 'Generation guide'],
    ...(videoFilename ? [[videoFilename, 'Final video']] : [['documentary_final_with_music.mp4', 'Final video']]),
  ];
  return (
    <section className="artifact-box">
      <div className="panel-kicker">PROJECT ARTIFACTS</div>
      {folder && <p className="artifact-folder">Saved in: {folder}</p>}
      <div className="artifact-list">
        {artifacts.map(([filename, label]) => (
          <a key={filename} className="text-link" href={downloadUrl(filename)} download>
            <Download size={15} /> {label}
          </a>
        ))}
      </div>
    </section>
  );
}

/* ─── Main App ───────────────────────────────────────────── */
function App() {
  const [authenticated, setAuthenticated] = useState(null);
  const [adminUsername, setAdminUsername] = useState('');
  const [userRole, setUserRole] = useState('admin');
  const [googleClientId, setGoogleClientId] = useState('');
  const [theme, setTheme] = useState(getInitialTheme);
  const [providerRequest, setProviderRequest] = useState(null);

  // Documentary state
  const [topic, setTopic] = useState('');
  const [genre, setGenre] = useState('history');
  const [visualStyle, setVisualStyle] = useState('photorealistic');
  const [scriptLanguage, setScriptLanguage] = useState('hindi');
  const [targetDuration, setTargetDuration] = useState(60);
  const [audioDuration, setAudioDuration] = useState(0);
  const [requiredImageCount, setRequiredImageCount] = useState(0);
  const [voice, setVoice] = useState('Iapetus');
  const [session, setSession] = useState(null);
  const [script, setScript] = useState('');
  const [prompts, setPrompts] = useState([]);
  const [generationPrompts, setGenerationPrompts] = useState('');
  const [files, setFiles] = useState([]);
  const [uploadResults, setUploadResults] = useState([]);
  const [uploadSummary, setUploadSummary] = useState(null);
  const [activeStep, setActiveStep] = useState(0);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [message, setMessage] = useState('Start by discovering a compelling topic.');
  const [skipModal, setSkipModal] = useState(null);
  const [audioUrl, setAudioUrl] = useState('');
  const [videoUrl, setVideoUrl] = useState('');
  const [videoFilename, setVideoFilename] = useState('');
  const [musicTrack, setMusicTrack] = useState('');
  const [scriptSaved, setScriptSaved] = useState(false);
  const IMAGE_SECONDS = 5;
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

  useEffect(() => {
    const handler = (event) => setProviderRequest(event.detail);
    window.addEventListener('provider-required', handler);
    return () => window.removeEventListener('provider-required', handler);
  }, []);

  const onLogin = (username, role) => { 
    setAdminUsername(username); 
    setUserRole(role); 
    setAuthenticated(true);
    // Re-fetch auth state after login to get session data
    requestJson('/api/auth/me').then((result) => {
      setAdminUsername(result.username || username);
      setUserRole(result.role || role);
      setGoogleClientId(result.google_configured ? (result.google_client_id || '') : '');
    }).catch(() => {});
  };

  if (authenticated === null) return (
    <main className="auth-shell"><div className="auth-loading">Checking studio access…</div></main>
  );
  if (!authenticated) return (
    <LoginScreen
      googleConfigured={googleClientId}
      onLogin={onLogin}
    />
  );

  const logout = async () => {
    await requestJson('/api/auth/logout', { method: 'POST' });
    setAuthenticated(false);
    setAdminUsername('');
  };
  const toggleTheme = () => setTheme((c) => c === 'light' ? 'dark' : 'light');
  const run = async (key, fn) => {
    setBusy(key); setError('');
    try { await fn(); } catch (err) { setError(err.message); } finally { setBusy(''); }
  };

  // ── Step handlers ──────────────────────────────────────────

  const handleTopicSelected = (selectedTopic, selectedGenre, selectedLanguage) => {
    setTopic(selectedTopic);
    setGenre(selectedGenre);
    if (selectedLanguage) setScriptLanguage(selectedLanguage);
    setActiveStep(1);
    setMessage('Topic locked in. Set the editorial parameters and open the story room.');
  };

  const ensureSession = async () => {
    if (session?.session_id) return session;
    if (!topic.trim()) throw new Error('Give the documentary a topic first.');
    const result = await requestJson('/api/create-session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        topic, genre, visual_style: visualStyle, script_language: scriptLanguage,
        target_duration: targetDuration,
        transition_seconds: transitionSeconds, narration_volume: narrationVolume, bgm_volume: bgmVolume,
      }),
    });
    setSession(result);
    setRequiredImageCount(Number(result.required_image_count || Math.max(1, Math.ceil(Number(targetDuration || 0) / IMAGE_SECONDS))));
    return result;
  };

  const createSession = (event) => {
    event.preventDefault();
    if (!topic.trim()) { setError('Give the documentary a topic first.'); return; }
    run('session', async () => {
      await ensureSession();
      setActiveStep(2);
      setMessage('The workspace is ready. Shape the voice of the story next.');
    });
  };

  const goToScript = () => run('session', async () => {
    await ensureSession();
    setActiveStep(2);
    setMessage('The workspace is ready. Shape the voice of the story next.');
  });

  const generateScript = () => run('script', async () => {
    const activeSession = await ensureSession();
    const result = await requestJson('/api/generate-script', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSession.session_id, topic, genre, script_language: scriptLanguage, target_duration: targetDuration }),
    });
    setScript(result.script);
    setScriptSaved(false);
    setMessage('Script drafted. Review it, save it, then move to narration.');
  });

  const saveScript = () => run('save-script', async () => {
    const activeSession = await ensureSession();
    const result = await requestJson('/api/update-script', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSession.session_id, script }),
    });
    setScript(result.script);
    setScriptSaved(true);
    setMessage('Script edits saved.');
  });

  const generateAudio = (useDefaultVoice = false) => run('audio', async () => {
    const activeSession = await ensureSession();
    // React passes the click event when this function is used directly as onClick.
    // Never allow that DOM/SVG event object into JSON.stringify().
    const defaultVoice = useDefaultVoice === true;
    const result = await requestJson('/api/generate-audio', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSession.session_id, voice, use_default_voice: defaultVoice }),
    });
    setAudioUrl(result.audio_url);
    setAudioDuration(Number(result.duration || 0));
    setRequiredImageCount(Number(result.image_count || 0));
    setActiveStep(3);
    setMessage(`One narration clip ready: ${Number(result.duration || 0).toFixed(1)} seconds. ${result.image_count} images are required.`);
  });

  const generatePrompts = () => run('prompts', async () => {
    const activeSession = await ensureSession();
    const result = await requestJson('/api/generate-prompts', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ session_id: activeSession.session_id, visual_style: visualStyle, transition_seconds: transitionSeconds, narration_volume: narrationVolume }),
    });
    setPrompts(result.prompts || []);
    setGenerationPrompts(result.generation_prompts || '');
    setActiveStep(4);
    setMessage(`${result.prompts.length} image prompts ready.`);
  });

  const uploadImages = () => run('upload', async () => {
    if (!files.length) throw new Error('Choose the generated images first.');
    const activeSession = await ensureSession();
    const formData = new FormData();
    formData.append('session_id', activeSession.session_id);
    files.forEach((file) => formData.append('files', file));
    const result = await requestJson('/api/upload-images', { method: 'POST', body: formData });
    setUploadResults(result.results || []);
    setUploadSummary({
      uploaded: result.uploaded_count || 0,
      required: result.required_count || prompts.length,
      missing: result.missing_numbers || [],
    });
    const missingNumbers = result.missing_numbers || [];
    setActiveStep(6);
    setMessage(missingNumbers.length
      ? `Upload the missing images: ${missingNumbers.join(', ')}.`
      : 'Images in sequence. Assemble the film when ready.');
  });

  const buildVideo = () => run('video', async () => {
    const activeSession = await ensureSession();
    const result = await requestJson('/api/build-video', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: activeSession.session_id,
        transition_seconds: transitionSeconds,
        narration_volume: narrationVolume,
        bgm_volume: bgmVolume,
      }),
    });
    setVideoUrl(result.video_url || result.download_url);
    setVideoFilename(result.video_filename || '');
    setMusicTrack(result.music_track || '');
    setMessage('Documentary finished. Download it and publish your story.');
  });

  const downloadUrl = (filename) => session ? `/api/session/${session.session_id}/download/${filename}` : '#';

  // ── Render ─────────────────────────────────────────────────
  return (
    <main className="app-shell">
      <ApiKeyModal
        request={providerRequest}
        onClose={() => setProviderRequest(null)}
        onSaved={(savedProvider) => { if (savedProvider === 'gemini' && providerRequest?.purpose === 'audio') setTimeout(() => generateAudio(false), 0); }}
        onUseDefaultVoice={() => setTimeout(() => generateAudio(true), 0)}
      />
      <SkipToStepModal
        targetStep={skipModal?.targetStep}
        blocker={skipModal?.blocker}
        onClose={() => setSkipModal(null)}
        onConfirm={async ({ audioFile, imageFiles, settings }) => {
          const activeSession = await ensureSession();
          // Handle audio upload if provided
          if (audioFile) {
            const formData = new FormData();
            formData.append('session_id', activeSession.session_id);
            formData.append('audio', audioFile);
            const result = await requestJson('/api/upload-audio', { method: 'POST', body: formData });
            setAudioUrl(result.audio_url);
            setAudioDuration(Number(result.duration || 0));
            setRequiredImageCount(Number(result.image_count || 0));
          }
          // Handle image upload if provided
          if (imageFiles.length > 0) {
            const formData = new FormData();
            formData.append('session_id', activeSession.session_id);
            imageFiles.forEach((file) => formData.append('files', file));
            const result = await requestJson('/api/upload-images', { method: 'POST', body: formData });
            setUploadResults(result.results || []);
            setUploadSummary({
              uploaded: result.uploaded_count || 0,
              required: result.required_count || prompts.length,
              missing: result.missing_numbers || [],
            });
          }
          // Apply settings if provided
          if (settings) {
            setTransitionSeconds(settings.transitionSeconds);
            setNarrationVolume(settings.narrationVolume);
            setBgmVolume(settings.bgmVolume);
          }
          setActiveStep(skipModal.targetStep);
        }}
      />
      <header className="masthead">
        <div className="brand-mark"><Clapperboard size={20} /> DOCUMENTARY STUDIO</div>
        <div className="header-tools">
          <button className="api-key-header-button" onClick={() => setProviderRequest({provider:'groq', message:'Manage your saved Groq and Gemini API keys. Groq is the required primary provider; Gemini is used when Groq resources are exhausted.'})}><Sparkles size={14} /> API Keys</button>
          <button className="theme-toggle" onClick={toggleTheme} aria-label={`Switch to ${theme === 'light' ? 'dark' : 'light'} theme`}>
            {theme === 'light' ? <Moon size={15} /> : <Sun size={15} />}
            <span>{theme === 'light' ? 'Dark' : 'Light'}</span>
          </button>
          <div className="header-note">
            {adminUsername} · {userRole}{' '}
            <button className="logout-button" onClick={logout}><LogOut size={13} /> Sign out</button>
            <span>•</span>
            {session ? session.session_id.split('-')[0] : 'new project'}
          </div>
        </div>
      </header>

      <section className="hero-block">
        <div className="eyebrow"><Sparkles size={15} /> FROM IDEA TO CUT</div>
        <h1>Make the story<br /><em>watchable.</em></h1>
        <p>One guided workspace — from topic discovery and scripting to narration, visuals, and the final film.</p>
      </section>

      <nav className="stepper" aria-label="Documentary workflow">
        {steps.map((step) => {
          const accessible = canAccessStep(step.id, { topic, script, audioUrl, prompts, uploadResults });
          const blocker = getStepBlocker(step.id);
          const isLocked = !accessible && activeStep !== step.id;
          return (
            <button
              key={step.id}
              className={`${activeStep >= step.id ? 'active' : ''} ${activeStep === step.id ? 'current' : ''} ${isLocked ? 'locked' : ''}`}
              onClick={() => {
                if (accessible || activeStep === step.id) {
                  setActiveStep(step.id);
                } else if (isLocked) {
                  setSkipModal({ targetStep: step.id, blocker });
                }
              }}
              title={!accessible && blocker ? `Complete: ${blocker}` : ''}
              disabled={!accessible && activeStep !== step.id}
            >
              <span>{activeStep > step.id ? <Check size={13} /> : step.id}</span>
              {step.label}
              {!accessible && activeStep !== step.id && <Lock size={12} />}
            </button>
          );
        })}
      </nav>
      <div className="progress-track" aria-label={`Step ${activeStep} of ${steps.length - 1}`}>
        <span style={{ width: `${(activeStep / (steps.length - 1)) * 100}%` }} />
      </div>

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

          {/* ── Step 0: Discover ── */}
          {activeStep === 0 && (
            <TopicDiscovery
              onSelectTopic={handleTopicSelected}
              onSkip={() => { setActiveStep(1); setMessage('Enter your topic and open the story room.'); }}
            />
          )}

          {/* ── Step 1: Topic ── */}
          {activeStep === 1 && (
            <section className="panel intro-panel">
              <PanelHeading icon={<Clapperboard />} kicker="01 / BEGIN WITH THE SUBJECT" title="What should we<br /><em>remember?</em>" detail="Set the documentary topic and editorial parameters." />
              {topic ? (
                <div className="skip-banner">
                  <div className="skip-info">
                    <Check size={16} />
                    <div>
                      <strong>Topic already set:</strong> {topic}
                      <span>Genre: {genre} · Language: {scriptLanguage} · Style: {visualStyle}</span>
                    </div>
                  </div>
                  <div className="skip-actions">
                    <ActionButton secondary onClick={goToScript}>Skip to Script <ArrowRight size={15} /></ActionButton>
                    <ActionButton onClick={() => { setTopic(''); setActiveStep(1); }}>Change topic</ActionButton>
                  </div>
                  {session && (
                    <div className="artifact-downloads">
                      <span className="artifact-label">Artifacts:</span>
                      <a className="text-link" href={downloadUrl('topic.txt')} download><Download size={13} /> Topic</a>
                    </div>
                  )}
                </div>
              ) : (
                <form onSubmit={createSession}>
                  <label>
                    Documentary topic
                    <input autoFocus value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="The hidden engineering of the Taj Mahal" />
                  </label>
                  <label>
                    Editorial lens
                    <select value={genre} onChange={(e) => setGenre(e.target.value)}>
                      <option value="history">History</option>
                      <option value="nature">Nature</option>
                      <option value="biography">Biography</option>
                      <option value="science">Science</option>
                      <option value="culture">Culture</option>
                      <option value="technology">Technology</option>
                      <option value="architecture">Architecture</option>
                      <option value="archaeology">Archaeology</option>
                      <option value="investigative">Investigative</option>
                      <option value="human stories">Human stories</option>
                      <option value="food">Food and traditions</option>
                      <option value="arts">Arts and heritage</option>
                      <option value="environment">Environment</option>
                    </select>
                  </label>
                  <label>
                    Script language
                    <select value={scriptLanguage} onChange={(e) => setScriptLanguage(e.target.value)}>
                      <option value="hindi">Hindi</option>
                      <option value="english">English</option>
                      <option value="hinglish">Hinglish</option>
                      <option value="bengali">Bengali</option>
                      <option value="tamil">Tamil</option>
                      <option value="telugu">Telugu</option>
                      <option value="marathi">Marathi</option>
                      <option value="gujarati">Gujarati</option>
                      <option value="kannada">Kannada</option>
                      <option value="malayalam">Malayalam</option>
                      <option value="punjabi">Punjabi</option>
                    </select>
                  </label>
                  <label>
                    Visual type
                    <select value={visualStyle} onChange={(e) => setVisualStyle(e.target.value)}>
                      <option value="photorealistic">Photorealistic documentary</option>
                      <option value="cartoon">Cartoon animation</option>
                      <option value="anime">Anime illustration</option>
                      <option value="3d_animation">3D animation</option>
                      <option value="illustrated">Painted illustration</option>
                      <option value="archival">Archival film</option>
                      <option value="watercolor">Watercolor and ink</option>
                      <option value="graphic_novel">Graphic novel</option>
                      <option value="claymation">Clay animation</option>
                      <option value="noir">Documentary noir</option>
                    </select>
                  </label>
                  <label>
                    Target video seconds
                    <input type="number" min="20" max="600" step="5" value={targetDuration} onChange={(e) => setTargetDuration(e.target.value)} />
                  </label>
                  <div className="duration-preview">
                    <span>Required images</span>
                    <strong>{Math.max(1, Math.ceil(Number(targetDuration || 0) / IMAGE_SECONDS))}</strong>
                  </div>
                  <div className="info-callout">
                    <strong>Images are automatic.</strong>
                    <span>Enter only the target video duration. The required image count is calculated automatically.</span>
                  </div>
                  <div className="panel-actions" style={{ marginTop: 0 }}>
                    <ActionButton secondary onClick={() => setActiveStep(0)}>
                      <ArrowLeft size={15} /> Back to discover
                    </ActionButton>
                    <ActionButton type="submit" busy={busy === 'session'}>
                      Open the story room <ArrowRight size={17} />
                    </ActionButton>
                  </div>
                </form>
              )}
            </section>
          )}

          {/* ── Step 2: Script ── */}
          {activeStep === 2 && (
            <section className="panel">
              <PanelHeading icon={<FileText />} kicker="02 / SCRIPT" title="Find the thread." detail="A continuous spoken script, shaped around your subject and editorial lens." />
              {!topic ? (
                <div className="skip-banner warning">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Topic not set.</strong>
                    <span>Please complete Step 1 (Topic) first to generate a script.</span>
                  </div>
                  <ActionButton onClick={() => setActiveStep(1)}>Go to Topic <ArrowRight size={15} /></ActionButton>
                </div>
              ) : !script ? (
                <>
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(1)}><ArrowLeft size={15} /> Back to topic</ActionButton>
                    <ActionButton secondary onClick={() => setActiveStep(3)}>Skip to Narration <ArrowRight size={15} /></ActionButton>
                  </div>
                  <ActionButton onClick={generateScript} busy={busy === 'script'}>Generate {scriptLanguage} script <WandSparkles size={17} /></ActionButton>
                </>
              ) : (
                <>
                  <div className="skip-banner">
                    <div className="skip-info">
                      <Check size={16} />
                      <div>
                        <strong>Script ready</strong> ({script.length} chars)
                        <span>Language: {scriptLanguage} · {scriptSaved ? 'Saved' : 'Unsaved changes'}</span>
                      </div>
                    </div>
                    <ActionButton secondary onClick={() => setActiveStep(3)}>Skip to Narration <ArrowRight size={15} /></ActionButton>
                    <div className="artifact-downloads">
                      <span className="artifact-label">Artifacts:</span>
                      <a className="text-link" href={downloadUrl('documentary_script.txt')} download><Download size={13} /> Script</a>
                    </div>
                  </div>
                  <label className="edit-label">
                    Edit {scriptLanguage} script
                    <textarea className="large-text" value={script} onChange={(e) => { setScript(e.target.value); setScriptSaved(false); }} />
                  </label>
                  {scriptLanguage === 'hindi' && !hasDevanagari(script) && (
                    <div className="language-warning">This script is not Hindi. Regenerate it to replace the older draft.</div>
                  )}
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(1)}><ArrowLeft size={15} /> Back to topic</ActionButton>
                    <div className="inline-actions">
                      <ActionButton secondary onClick={generateScript} busy={busy === 'script'}><WandSparkles size={15} /> Regenerate</ActionButton>
                      <ActionButton secondary onClick={saveScript} busy={busy === 'save-script'}><Save size={15} /> {scriptSaved ? 'Saved' : 'Save changes'}</ActionButton>
                      <a className="text-link" href={downloadUrl('documentary_script.txt')} download><Download size={15} /> Download</a>
                      <ActionButton onClick={() => setActiveStep(3)}>Continue to narration <ArrowRight size={17} /></ActionButton>
                    </div>
                  </div>
                </>
              )}
            </section>
          )}

          {/* ── Step 3: Narration ── */}
          {activeStep === 3 && (
            <section className="panel">
              <PanelHeading icon={<Mic2 />} kicker="03 / NARRATION" title="Give it a voice." detail="Generate one continuous narration clip from the complete script. The required image count is calculated automatically from the target duration." />
              {!script ? (
                <div className="skip-banner warning">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Script not ready.</strong>
                    <span>Please complete Step 2 (Script) first to generate narration.</span>
                  </div>
                  <ActionButton onClick={() => setActiveStep(2)}>Go to Script <ArrowRight size={15} /></ActionButton>
                </div>
              ) : !audioUrl ? (
                <>
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(2)}><ArrowLeft size={15} /> Back to script</ActionButton>
                    <ActionButton secondary onClick={() => setActiveStep(4)}>Skip to Prompts <ArrowRight size={15} /></ActionButton>
                  </div>
                  <label>
                    Voice character
                    <select value={voice} onChange={(e) => setVoice(e.target.value)}>
                      <option>Iapetus</option>
                      <option>Kore</option>
                      <option>Zephyr</option>
                      <option>Nova</option>
                    </select>
                  </label>
                  <div className="audio-plan">
                    <div><span>Target duration</span><strong>{targetDuration} sec</strong></div>
                    <div><span>Required images</span><strong>{requiredImageCount || Math.max(1, Math.ceil(Number(targetDuration || 0) / IMAGE_SECONDS))}</strong></div>
                    <div><span>Audio clips</span><strong>1</strong></div>
                  </div>
                  <ActionButton onClick={() => generateAudio(false)} busy={busy === 'audio'}>Generate complete narration <Play size={17} /></ActionButton>
                </>
              ) : (
                <>
                  <div className="skip-banner">
                    <div className="skip-info">
                      <Check size={16} />
                      <div>
                        <strong>Narration ready</strong> ({audioDuration.toFixed(1)} sec)
                        <span>Voice: {voice} · Required images: {requiredImageCount}</span>
                      </div>
                    </div>
                    <ActionButton secondary onClick={() => setActiveStep(4)}>Skip to Prompts <ArrowRight size={15} /></ActionButton>
                    <div className="artifact-downloads">
                      <span className="artifact-label">Artifacts:</span>
                      <a className="text-link" href={audioUrl} download><Download size={13} /> Narration WAV</a>
                    </div>
                  </div>
                  <div className="audio-result-note">One narration clip: <strong>{audioDuration.toFixed(1)} seconds</strong> · Required images: <strong>{requiredImageCount}</strong></div>
                  <div className="media-strip">
                    <audio controls src={audioUrl} />
                    <a className="text-link" href={audioUrl} download><Download size={15} /> Download WAV</a>
                  </div>
                  <div className="panel-actions">
                    <ActionButton onClick={() => setActiveStep(4)}>Continue to image prompts <ArrowRight size={17} /></ActionButton>
                  </div>
                </>
              )}
            </section>
          )}

          {/* ── Step 4: Prompts ── */}
          {activeStep === 4 && (
            <section className="panel">
              <PanelHeading icon={<WandSparkles />} kicker="04 / VISUAL DIRECTION" title="Describe what we see." detail="Create numbered image prompts and a production brief for consistent generation." />
              {!audioUrl ? (
                <div className="skip-banner warning">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Narration not ready.</strong>
                    <span>Please complete Step 3 (Narration) first to generate image prompts.</span>
                  </div>
                  <ActionButton onClick={() => setActiveStep(3)}>Go to Narration <ArrowRight size={15} /></ActionButton>
                </div>
              ) : !prompts.length ? (
                <>
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(3)}><ArrowLeft size={15} /> Back to narration</ActionButton>
                    <ActionButton secondary onClick={() => setActiveStep(5)}>Skip to Image Bay <ArrowRight size={15} /></ActionButton>
                  </div>
                  <ActionButton onClick={generatePrompts} busy={busy === 'prompts'}>Generate image prompts <Sparkles size={17} /></ActionButton>
                </>
              ) : (
                <>
                  <div className="skip-banner">
                    <div className="skip-info">
                      <Check size={16} />
                      <div>
                        <strong>Prompts ready</strong> ({prompts.length} prompts)
                        <span>Visual style: {visualStyle}</span>
                      </div>
                    </div>
                    <ActionButton secondary onClick={() => setActiveStep(5)}>Skip to Image Bay <ArrowRight size={15} /></ActionButton>
                    <div className="artifact-downloads">
                      <span className="artifact-label">Artifacts:</span>
                      <a className="text-link" href={downloadUrl('image_prompts.txt')} download><Download size={13} /> Scene Prompts</a>
                      <a className="text-link" href={downloadUrl('image_generation_prompts.txt')} download><Download size={13} /> Generation Guide</a>
                    </div>
                  </div>
                  <FlowGuide prompts={prompts} generationPrompts={generationPrompts} downloadUrl={downloadUrl} />
                  <PromptReview prompts={prompts} generationPrompts={generationPrompts} downloadUrl={downloadUrl} onBack={() => setActiveStep(3)} onContinue={() => setActiveStep(5)} />
                </>
              )}
            </section>
          )}

          {/* ── Step 5: Image Bay ── */}
          {activeStep === 5 && (
            <section className="panel">
              <PanelHeading icon={<FileImage />} kicker="05 / IMAGE BAY" title="Bring the Flow frames here." detail="Use the Google Flow guide below, download the finished project, then upload the numbered images. No manual image count is required." />
              {!prompts.length ? (
                <div className="skip-banner warning">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Prompts not ready.</strong>
                    <span>Please complete Step 4 (Prompts) first to know what images to generate.</span>
                  </div>
                  <ActionButton onClick={() => setActiveStep(4)}>Go to Prompts <ArrowRight size={15} /></ActionButton>
                </div>
              ) : uploadResults.length === 0 ? (
                <>
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(4)}><ArrowLeft size={15} /> Back to prompts</ActionButton>
                    <ActionButton secondary onClick={() => setActiveStep(6)}>Skip to Final Cut <ArrowRight size={15} /></ActionButton>
                  </div>
                  <FlowGuide prompts={prompts} generationPrompts={generationPrompts} downloadUrl={downloadUrl} />
                  <div className="flow-to-upload-divider"><span>AFTER ALL FLOW IMAGES ARE GENERATED</span></div>
                  <div className="image-upload-card">
                    <div className="social-field-label"><Upload size={14} /> IMAGE BAY UPLOAD</div>
                    <p>Rename the exported Flow images to <strong>1.jpeg, 2.jpeg, 3.jpeg…</strong> using the provided command, refresh the Flow project, then use the <strong>three-dots menu → Download project</strong>. After downloading, select the numbered image files below.</p>
                    <label className="drop-zone">
                      <Upload size={24} />
                      <strong>{files.length ? `${files.length} images selected` : 'Choose the downloaded Flow images'}</strong>
                      <span>JPEG, PNG, or WEBP · no manual image-count entry required</span>
                      <input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
                    </label>
                    <div className="image-actions">
                      <ActionButton onClick={uploadImages} busy={busy === 'upload'} disabled={!files.length}>Upload images <ArrowRight size={17} /></ActionButton>
                    </div>
                  </div>
                </>
              ) : (
                <>
                  <div className="skip-banner">
                    <div className="skip-info">
                      <Check size={16} />
                      <div>
                        <strong>Images uploaded</strong> ({uploadResults.length} images)
                        <span>Missing: {uploadSummary?.missing?.length || 0}</span>
                      </div>
                    </div>
                    <ActionButton secondary onClick={() => setActiveStep(6)}>Skip to Final Cut <ArrowRight size={15} /></ActionButton>
                    <div className="artifact-downloads">
                      <span className="artifact-label">Artifacts:</span>
                      <a className="text-link" href={downloadUrl('image_prompts.txt')} download><Download size={13} /> Scene Prompts</a>
                      <a className="text-link" href={downloadUrl('image_generation_prompts.txt')} download><Download size={13} /> Generation Guide</a>
                    </div>
                  </div>
                  <FlowGuide prompts={prompts} generationPrompts={generationPrompts} downloadUrl={downloadUrl} />
                  <div className="flow-to-upload-divider"><span>AFTER ALL FLOW IMAGES ARE GENERATED</span></div>
                  <div className="image-upload-card">
                    <div className="social-field-label"><Upload size={14} /> IMAGE BAY UPLOAD</div>
                    <p>Rename the exported Flow images to <strong>1.jpeg, 2.jpeg, 3.jpeg…</strong> using the provided command, refresh the Flow project, then use the <strong>three-dots menu → Download project</strong>. After downloading, select the numbered image files below.</p>
                    <label className="drop-zone">
                      <Upload size={24} />
                      <strong>{files.length ? `${files.length} images selected` : 'Choose the downloaded Flow images'}</strong>
                      <span>JPEG, PNG, or WEBP · no manual image-count entry required</span>
                      <input type="file" multiple accept="image/jpeg,image/png,image/webp" onChange={(e) => setFiles(Array.from(e.target.files || []))} />
                    </label>
                    <div className="image-actions">
                      <ActionButton onClick={uploadImages} busy={busy === 'upload'} disabled={!files.length}>Upload images <ArrowRight size={17} /></ActionButton>
                    </div>
                    {uploadResults.length > 0 && <div className="upload-list">{uploadResults.map((item) => <div key={`${item.name}-${item.target}`}><Check size={15} /> {item.name} <span>{item.target || item.reason}</span></div>)}</div>}
                  </div>
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(4)}><ArrowLeft size={15} /> Back to prompts</ActionButton>
                    <ActionButton onClick={() => setActiveStep(6)}>Continue to Final Cut <ArrowRight size={17} /></ActionButton>
                  </div>
                </>
              )}
            </section>
          )}

          {/* ── Step 6: Final Cut + Social ── */}
          {activeStep === 6 && (
            <section className="panel finish-panel">
              <PanelHeading icon={<Film />} kicker="06 / FINAL CUT" title="Roll the film." detail="Set the transition and audio mix, then render the documentary. Visual timing is fixed internally at 5 seconds." />
              {!uploadResults.length ? (
                <div className="skip-banner warning">
                  <AlertTriangle size={16} />
                  <div>
                    <strong>Images not uploaded.</strong>
                    <span>Please complete Step 5 (Image Bay) first to upload images before assembling the video.</span>
                  </div>
                  <ActionButton onClick={() => setActiveStep(5)}>Go to Image Bay <ArrowRight size={15} /></ActionButton>
                </div>
              ) : !videoUrl ? (
                <>
                  <div className="panel-actions">
                    <ActionButton secondary onClick={() => setActiveStep(5)}><ArrowLeft size={15} /> Back to Image Bay</ActionButton>
                  </div>
                  <div className="render-settings">
                    <label>Transition seconds<input type="number" min="0" max="10" step="0.1" value={transitionSeconds} onChange={(e) => setTransitionSeconds(e.target.value)} /></label>
                    <label>Narration volume<input type="number" min="0" max="3" step="0.1" value={narrationVolume} onChange={(e) => setNarrationVolume(e.target.value)} /></label>
                    <label>BGM volume<input type="number" min="0" max="1" step="0.05" value={bgmVolume} onChange={(e) => setBgmVolume(e.target.value)} /></label>
                  </div>
                  <ActionButton onClick={buildVideo} busy={busy === 'video'}>Assemble documentary <Film size={17} /></ActionButton>
                </>
              ) : (
                <>
                  <div className="skip-banner">
                    <div className="skip-info">
                      <Check size={16} />
                      <div>
                        <strong>Video ready</strong> ({videoFilename || 'documentary.mp4'})
                        <span>{musicTrack ? `BGM: ${musicTrack}` : 'No BGM'}</span>
                      </div>
                    </div>
                  </div>
                  <div className="video-wrap">
                    <video controls src={videoUrl} />
                    <div className="video-meta">
                      <span><span className="live-dot" /> FINAL CUT READY</span>
                      {musicTrack && <span>BGM · {musicTrack}</span>}
                      <a className="text-link" href={videoUrl} download><Download size={15} /> Download MP4</a>
                    </div>
                  </div>
                  <ArtifactDownloads downloadUrl={downloadUrl} folder={session?.folder} videoFilename={videoFilename} />
                  {/* Social media copy — shown after video is ready */}
                  <SocialMediaPanel sessionId={session?.session_id} />
                </>
              )}
            </section>
          )}
        </div>
      </section>
    </main>
  );
}

export default App;
