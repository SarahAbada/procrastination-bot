const axios = require('axios');
const express = require('express');
require('dotenv').config();

const app = express();
const port = process.env.PORT || 3000;

const BRIGHTSPACE_HOST = "https://uottawa.brightspace.com";

const getHeaders = () => ({
  'Cookie': `d2lSessionVal=${process.env.D2L_SESSION_VAL}; d2lSecureSessionVal=${process.env.D2L_SECURE_SESSION_VAL}`,
  'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
});

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
    res.status(500).json({ error: "Failed to fetch. Cookies might be expired.", details: error.message });
  }
});

app.listen(port, () => console.log(`🚀 Bridge running on http://localhost:${port}`));