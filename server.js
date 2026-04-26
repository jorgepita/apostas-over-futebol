const express = require('express');
const cors = require('cors');

const app = express();

/* =========================
   CONFIG
========================= */
const PORT = process.env.PORT || 3000;

const ALLOWED_ORIGINS = [
  'https://jorgepita.github.io',
  'http://localhost:3000',
  'http://127.0.0.1:3000'
];

/* =========================
   MIDDLEWARE
========================= */

const corsOptions = {
  origin: function (origin, callback) {
    if (!origin) return callback(null, true);

    const allowed = [
      'https://jorgepita.github.io',
      'http://localhost:3000',
      'http://127.0.0.1:3000'
    ];

    if (allowed.includes(origin)) {
      callback(null, true);
    } else {
      console.warn('CORS bloqueado para:', origin);
      callback(null, false);
    }
  },
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
};

app.use(cors(corsOptions));
app.options('*', cors(corsOptions));

// JSON body parser
app.use(express.json({ limit: '1mb' }));

/* =========================
   HEALTH CHECK
========================= */
app.get('/', (req, res) => {
  res.json({ status: 'ok', service: 'cloud-save-api' });
});

/* =========================
   SAVE ENDPOINT
========================= */
app.post('/save', async (req, res) => {
  try {
    const { content, message = 'update cloud state' } = req.body;

    if (!content) {
      return res.status(400).json({
        error: 'Missing content'
      });
    }

    const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
    const REPO = process.env.GITHUB_REPO; // ex: jorgepita/apostas-over-futebol
    const FILE_PATH = 'cloud_state.json';

    if (!GITHUB_TOKEN || !REPO) {
      return res.status(500).json({
        error: 'Missing env vars (GITHUB_TOKEN or GITHUB_REPO)'
      });
    }

    const apiUrl = `https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`;

    // timeout helper
    const fetchWithTimeout = (url, options, timeout = 10000) =>
      Promise.race([
        fetch(url, options),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), timeout)
        )
      ]);

    // 1. GET sha atual (se existir)
    let sha = null;

    const getRes = await fetchWithTimeout(apiUrl, {
      headers: {
        Authorization: `token ${GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json'
      }
    });

    if (getRes.status === 200) {
      const data = await getRes.json();
      sha = data.sha;
    }

    // 2. Converter conteúdo para base64
    const encodedContent = Buffer.from(
      JSON.stringify(content, null, 2)
    ).toString('base64');

    // 3. PUT (criar ou atualizar)
    const putRes = await fetchWithTimeout(apiUrl, {
      method: 'PUT',
      headers: {
        Authorization: `token ${GITHUB_TOKEN}`,
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({
        message,
        content: encodedContent,
        sha
      })
    });

    const result = await putRes.json();

    if (!putRes.ok) {
      console.error('GitHub error:', result);
      return res.status(500).json({
        error: 'GitHub API error',
        details: result
      });
    }

    console.log('Saved to GitHub:', FILE_PATH);

    return res.json({
      success: true,
      sha: result.content.sha
    });

  } catch (err) {
    console.error('SAVE ERROR:', err);

    return res.status(500).json({
      error: err.message || 'Internal error'
    });
  }
});

/* =========================
   ERROR HANDLER GLOBAL
========================= */
app.use((err, req, res, next) => {
  console.error('GLOBAL ERROR:', err.message);
  res.status(500).json({ error: err.message });
});

/* =========================
   START
========================= */
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
