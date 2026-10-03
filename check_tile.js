const fs = require('fs');

async function checkTile() {
  const url = 'https://cdnil.govmap.gov.il/xyz/heb/10/612/416.png';
  try {
    const res = await fetch(url);
    console.log('Status:', res.status);
    console.log('Content-Type:', res.headers.get('content-type'));
    if (res.status === 200) {
      const buffer = await res.arrayBuffer();
      fs.writeFileSync('tile.png', Buffer.from(buffer));
      console.log('Tile saved as tile.png');
    }
  } catch (err) {
    console.error('Error fetching tile:', err.message);
  }
}
checkTile();
