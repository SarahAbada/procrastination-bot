const axios = require('axios');
const express = require('express');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 3000;

const BRIGHTSPACE_HOST = "https://uottawa.brightspace.com";

// --- Auth middleware: every request must carry the shared secret ---
// This prevents anything else in the Docker network from hitting the bridge
app.use((req, res, next) => {
  const token = req.headers['x-bridge-token'];
  if (!token || token !== process.env.BRIDGE_SECRET) {
    return res.status(401).json({ error: 'Unauthorized' });
  }
  next();
});

const getHeaders = () => ({
  'Cookie': `d2lSessionVal=${process.env.D2L_SESSION_VAL}; d2lSecureSessionVal=${process.env.D2L_SECURE_SESSION_VAL}`,
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
});
// GET only — no POST/PUT/DELETE routes exist, so they can't be called
// Endpoint 1: Get raw upcoming events/deadlines
app.get('/deadlines', async (req, res) => {
  try {
    const url = `${BRIGHTSPACE_HOST}/d2l/api/lp/1.30/feed/`;
    const response = await axios.get(url, { headers: getHeaders() });
    
    // Minimal mapping to reduce token usage for the AI
    const tasks = response.data.Objects.map(obj => ({
      title: obj.Title,
      due: obj.EndDate,
      link: obj.Url,
      type: obj.Type
    }));

    res.json(tasks);
  } catch (error) {
     // Don't leak internal error details to the caller
    console.error('Brightspace fetch failed:', error.message);
    res.status(502).json({ error: "Failed to fetch from Brightspace. Cookies may be expired." });

}});
// Catch-all: return 404 for anything the agent tries that doesn't exist
app.use((req, res) => {
  res.status(404).json({ error: 'Not found' });
});

app.listen(port, '0.0.0.0', () => console.log(`Bridge running on port ${port}`));
