'use strict';
// The shape Muse accepts on the same chat-completions call server.js already makes.
// A 640px JPEG is one image_url on the current user message. Older shots are not resent.

function userContent(text, image) {
  const cue = String(text || '');
  const url = String(image || '').trim();
  if (!url.startsWith('data:image/')) return cue;
  return [
    { type: 'text', text: cue },
    { type: 'image_url', image_url: { url } },
  ];
}

module.exports = { userContent };
