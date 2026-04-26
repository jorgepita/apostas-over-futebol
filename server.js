const express = require('express');
const cors = require('cors');
const fs = require('fs');

const app = express();

app.use(cors());
app.use(express.json());

const FILE = 'data.json';

app.get('/load', (req, res) => {
  try {
    if (!fs.existsSync(FILE)) return res.json({});
    const data = JSON.parse(fs.readFileSync(FILE));
    res.json(data);
  } catch {
    res.status(500).json({ error: 'load error' });
  }
});

app.post('/save', (req, res) => {
  try {
    fs.writeFileSync(FILE, JSON.stringify(req.body, null, 2));
    res.json({ ok: true });
  } catch {
    res.status(500).json({ error: 'save error' });
  }
});

const PORT = process.env.PORT || 3000;
app.listen(PORT, () => console.log('server running'));
