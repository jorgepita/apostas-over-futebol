const express = require('express');
const cors = require('cors');

const app = express();

/* =========================
   CONFIG
========================= */
const PORT = process.env.PORT || 3000;

/* =========================
   MIDDLEWARE
========================= */
app.use(cors({
  origin: '*',
  methods: ['GET', 'POST', 'OPTIONS'],
  allowedHeaders: ['Content-Type', 'Authorization']
}));

app.use(express.json({ limit: '1mb' }));

/* =========================
   HEALTH CHECK
========================= */
app.get('/', (req, res) => {
  res.json({
    status: 'ok',
    service: 'cloud-save-api'
  });
});

/* =========================
   SAVE ENDPOINT
========================= */
app.post('/save', async (req, res) => {
  try {
    console.log('BODY:', req.body);

    const { content, message = 'update cloud state' } = req.body;

    if (!content) {
      return res.status(400).json({
        error: 'Missing content'
      });
    }

    const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
    const REPO = process.env.GITHUB_REPO;
    const FILE_PATH = 'cloud_state.json';

    if (!GITHUB_TOKEN || !REPO) {
      return res.status(500).json({
        error: 'Missing env vars (GITHUB_TOKEN or GITHUB_REPO)'
      });
    }

    const apiUrl = `https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`;

    const fetchWithTimeout = (url, options, timeout = 10000) =>
      Promise.race([
        fetch(url, options),
        new Promise((_, reject) =>
          setTimeout(() => reject(new Error('Timeout')), timeout)
        )
      ]);

    // obter SHA atual
    let sha = null;

    const getRes = await fetchWithTimeout(apiUrl, {
      headers: {
        Authorization: `Bearer ${GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json'
      }
    });

    if (getRes.status === 200) {
      const data = await getRes.json();
      sha = data.sha;
    }

    // converter conteúdo para base64
    const encodedContent = Buffer.from(
      JSON.stringify(content, null, 2)
    ).toString('base64');

    // criar / atualizar ficheiro
    const putRes = await fetchWithTimeout(apiUrl, {
      method: 'PUT',
      headers: {
        Authorization: `Bearer ${GITHUB_TOKEN}`,
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
      console.error('GitHub SAVE error:', result);

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
   LOAD ENDPOINT
========================= */
app.get('/load', async (req, res) => {
  try {
    const GITHUB_TOKEN = process.env.GITHUB_TOKEN;
    const REPO = process.env.GITHUB_REPO;
    const FILE_PATH = 'cloud_state.json';

    if (!GITHUB_TOKEN || !REPO) {
      return res.status(500).json({
        error: 'Missing env vars (GITHUB_TOKEN or GITHUB_REPO)'
      });
    }

    const apiUrl = `https://api.github.com/repos/${REPO}/contents/${FILE_PATH}`;

    const response = await fetch(apiUrl, {
      headers: {
        Authorization: `Bearer ${GITHUB_TOKEN}`,
        Accept: 'application/vnd.github+json'
      }
    });

    // ficheiro ainda não existe
    if (response.status === 404) {
      return res.json({});
    }

    const data = await response.json();

    if (!response.ok) {
      console.error('GitHub LOAD error:', data);

      return res.status(500).json({
        error: 'GitHub API error',
        details: data
      });
    }

    const content = JSON.parse(
      Buffer.from(data.content, 'base64').toString('utf-8')
    );

    return res.json(content);

  } catch (err) {
    console.error('LOAD ERROR:', err);

    return res.status(500).json({
      error: err.message || 'Internal error'
    });
  }
});

/* =========================
   GLOBAL ERROR HANDLER
========================= */
app.use((err, req, res, next) => {
  console.error('GLOBAL ERROR:', err);

  res.status(500).json({
    error: err.message || 'Internal server error'
  });
});

/* =========================
   START SERVER
========================= */
app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});
