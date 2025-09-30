import http from 'k6/http';
import { sleep } from 'k6';
import { check } from 'k6';

// k6 script to simulate many concurrent video playback clients.
// Example run:
//  k6 run --vus 100 --duration 1m jitlab/tools/k6_video_stream.js

const URL_PATH = '/videos/video.mp4';
const BASE = __ENV.BASE || 'http://localhost:8080';
const CHUNK_SIZE = parseInt(__ENV.CHUNK_SIZE || '1048576'); // bytes

function getTotal() {
  const r = http.head(`${BASE}${URL_PATH}`);
  if (r.status === 200) {
    const cl = r.headers['Content-Length'];
    return parseInt(cl || '0');
  }
  return 0;
}

export default function () {
  const total = getTotal();
  if (!total) {
    http.get(`${BASE}${URL_PATH}`);
    sleep(Math.random());
    return;
  }

  // simulate initial probe
  http.head(`${BASE}${URL_PATH}`);

  // pick random start
  let start = Math.floor(Math.random() * Math.max(1, total - 1));
  const chunks = Math.floor(Math.random() * 20) + 3;

  for (let i = 0; i < chunks; i++) {
    if (start >= total) break;
    const end = Math.min(start + CHUNK_SIZE - 1, total - 1);
    const res = http.get(`${BASE}${URL_PATH}`, { headers: { Range: `bytes=${start}-${end}` } });
    check(res, { 'status is 206 or 200': (r) => r.status === 206 || r.status === 200 });
    // simulate inter-chunk play interval
    sleep(Math.random() * 0.1);
    if (Math.random() < 0.05) {
      // seek
      start = Math.floor(Math.random() * Math.max(1, total - 1));
    } else {
      start = end + 1;
    }
  }
  sleep(Math.random() * 2);
}
