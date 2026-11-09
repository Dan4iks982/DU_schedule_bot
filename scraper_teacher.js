const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const DATA_DIR = path.join(__dirname, 'data');
const TEACHERS_DIR = path.join(DATA_DIR, 'teachers');
if (!fs.existsSync(TEACHERS_DIR)) {
  fs.mkdirSync(TEACHERS_DIR, { recursive: true });
}

async function scrapeTeacher(teacherId, teacherName) {
  const chromePath = process.env.PUPPETEER_EXECUTABLE_PATH || 
    (process.platform === 'win32' 
      ? 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe' 
      : '/usr/bin/chromium');

  const browser = await puppeteer.launch({
    executablePath: chromePath,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage', '--disable-gpu']
  });

  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1400, height: 1000 });

    await page.goto('https://luis.lu.lv/pls/du/pub_nod.main?l=1&p_au=D&p_mg=FO0064#skatit', {
      waitUntil: 'networkidle2',
      timeout: 30000
    });

    await page.evaluate(() => {
      const cb = document.querySelector('input[name="p_det"][value="psn"]');
      if (cb) cb.checked = true;
      const btn = Array.from(document.querySelectorAll('input[type=submit]')).find(b => b.value === 'Pievienot');
      if (btn) btn.click();
    });

    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 25000 });

    // Type teacher name
    const queryPart = teacherName.trim().split(' ').pop(); // last name
    await page.type('#p_pas_input', queryPart);
    await new Promise(r => setTimeout(r, 1500));

    const clicked = await page.evaluate((tName) => {
      const picker = document.querySelector('#p_pas_input').closest('.multi-picker');
      if (!picker) return false;
      const items = Array.from(picker.querySelectorAll('li'));
      const target = items.find(li => li.innerText.includes(tName) || li.innerText.includes(tName.split(' ').pop()));
      if (target) {
        (target.querySelector('.multi-elem-base-value') || target).click();
        return true;
      }
      return false;
    }, teacherName);

    await new Promise(r => setTimeout(r, 800));

    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('input[type=submit]')).find(b => b.value === 'Skatīt');
      if (btn) btn.click();
    });

    await page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 25000 });

    const events = await page.evaluate(() => {
      const calEl = document.querySelector('.fc, [id*=calendar]');
      if (window.$ && calEl) {
        const items = window.$(calEl).fullCalendar('clientEvents');
        return items.map(e => ({
          id: e.id,
          title: e.title,
          start: e.start ? e.start.toString() : '',
          end: e.end ? e.end.toString() : '',
          raw: e.raw || {}
        }));
      }
      return [];
    });

    const outFile = path.join(TEACHERS_DIR, `events_${teacherId}.json`);
    fs.writeFileSync(outFile, JSON.stringify(events, null, 2), 'utf-8');
    console.log(JSON.stringify({ success: true, count: events.length, file: outFile }));
    return events;
  } catch (err) {
    console.error(JSON.stringify({ success: false, error: err.message }));
    return [];
  } finally {
    await browser.close();
  }
}

const args = process.argv.slice(2);
const tId = args[0] || '116674';
const tName = args[1] || 'Aleksejs Ruža';
scrapeTeacher(tId, tName);
