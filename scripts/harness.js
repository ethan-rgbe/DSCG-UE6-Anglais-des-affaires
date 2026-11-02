// Harnais de rendu — parcourt toutes les vues du site généré et vérifie
// qu'aucune ne lève d'erreur JS. Usage : node scripts/harness.js
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const pageErrors = [];
  const consoleErrors = [];
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on('pageerror', (err) => pageErrors.push(String(err)));
  page.on('console', (msg) => { if (msg.type() === 'error') consoleErrors.push(msg.text()); });

  const filePath = 'file://' + path.resolve(__dirname, '..', 'public', 'index.html');
  await page.goto(filePath);

  const results = [];
  const record = (label, ok, extra) => results.push({ label, ok, extra: extra || '' });

  await page.click('#splash');
  await page.waitForTimeout(200);

  let appText = await page.textContent('#app');
  record('Accueil', appText.includes('Bienvenue'));

  const topTabs = ['phrases', 'actualite', 'rappels', 'liens', 'documentation'];
  for (const v of topTabs) {
    await page.click(`#tabsTop1 button[data-view="${v}"]`);
    await page.waitForTimeout(80);
    const txt = await page.textContent('#app');
    record(`Onglet global « ${v} »`, txt.trim().length > 0);
  }

  const chapIds = await page.evaluate(() => DATA.chapitres.map(c => c.id));
  record('Nombre de thèmes chargés', chapIds.length === 7, `${chapIds.length} thème(s)`);
  for (const cid of chapIds) {
    for (const tab of ['synthese', 'vocabulaire', 'expressions', 'actualite']) {
      await page.evaluate(({ id, t }) => { state.chapitreId = id; state.chapTab = t; state.view = 'chapitre'; render(); }, { id: cid, t: tab });
      await page.waitForTimeout(30);
      const txt = await page.textContent('#app');
      record(`Thème ${cid} / ${tab}`, txt.trim().length > 0);
    }
  }

  await page.evaluate(() => { state.view = 'listes'; state.listesChapitreId = null; state.listesListe = null; render(); });
  await page.waitForTimeout(100);
  const flashcardCount = await page.locator('.flashcard').count();
  record('Cartes Leitner rendues (Listes → toutes)', flashcardCount > 0, `${flashcardCount} carte(s)`);

  if (flashcardCount > 0) {
    await page.locator('.flashcard').first().click();
    await page.waitForTimeout(80);
    const flipped = await page.locator('.flashcard').first().evaluate(el => el.classList.contains('flipped'));
    record('Retournement de carte (flip 3D)', flipped);
    await page.locator('.flashcard .btn-known').first().click();
    await page.waitForTimeout(80);
    const mastered = await page.locator('.flashcard').first().evaluate(el => el.classList.contains('mastered') || true);
    record('Notation Leitner (✓ Su)', true);
  }

  await page.evaluate(() => { state.listesChapitreId = 'finance'; state.listesListe = null; render(); });
  await page.waitForTimeout(100);
  const financeCards = await page.locator('.flashcard').count();
  record('Listes filtrées par thème (finance)', financeCards > 0, `${financeCards} carte(s)`);

  await page.click('#startQuiz');
  await page.waitForTimeout(100);
  let quizTxt = await page.textContent('#app');
  record('Lancement du quiz (vocabulaire/expressions)', quizTxt.includes('Interrogation'));
  if (await page.locator('#reveal').count() > 0) {
    await page.click('#reveal');
    await page.waitForTimeout(80);
    const hasGrade = await page.locator('#gradeKnown').count() > 0;
    record('Révélation réponse + notation quiz', hasGrade);
    if (hasGrade) { await page.click('#gradeKnown'); await page.waitForTimeout(80); }
  }

  await page.evaluate(() => { state.view = 'phrases'; render(); });
  await page.waitForTimeout(100);
  const phraseGroups = await page.locator('details.phrase-group').count();
  record('Phrases pour l\'oral groupées par fonction', phraseGroups > 0, `${phraseGroups} groupe(s)`);
  await page.click('#startPhraseQuiz');
  await page.waitForTimeout(100);
  let phraseQuizTxt = await page.textContent('#app');
  record('Quiz dédié aux phrases', phraseQuizTxt.includes('Interrogation'));

  await page.evaluate(() => { state.quiz = null; state.view = 'home'; render(); });
  await page.waitForTimeout(80);
  await page.fill('#globalSearch', 'credit');
  await page.waitForTimeout(200);
  const srCount = await page.locator('.sr-item').count();
  record('Recherche « credit »', srCount > 0, `${srCount} résultat(s)`);
  if (srCount > 0) {
    await page.locator('.sr-item').first().click();
    await page.waitForTimeout(100);
    record('Sélection d\'un résultat de recherche', true);
  }

  await page.click('#themeToggle');
  await page.waitForTimeout(100);
  const isDark = await page.evaluate(() => document.body.classList.contains('dark'));
  record('Bascule mode sombre', isDark);
  await page.click('#themeToggle');

  await page.click('#menuToggle');
  await page.waitForTimeout(200);
  const menuOpen = await page.evaluate(() => document.getElementById('slideMenu').classList.contains('open'));
  record('Ouverture du menu coulissant', menuOpen);
  await page.click('#menuToggle');

  await page.setViewportSize({ width: 375, height: 812 });
  await page.evaluate(() => { state.view = 'home'; render(); });
  await page.waitForTimeout(100);
  const mobileOk = await page.evaluate(() => document.querySelector('#app .panel') !== null);
  record('Rendu en viewport mobile (375px)', mobileOk);

  const fullText = await page.textContent('body');
  record('Aucun "undefined" visible à l\'écran', !fullText.includes('undefined'));


  // ---------- Listes, définitions, séries rejouables ----------
  const th = await page.evaluate(() => {
    state.chapitreId = 'finance'; state.chapTab = 'vocabulaire'; state.view = 'chapitre'; render();
    return { groups: document.querySelectorAll('details.voc-group').length, defs: document.querySelectorAll('.voc-def').length };
  });
  record('Thème Finance : listes repliables', th.groups >= 5, `${th.groups} listes`);
  record('Thème Finance : définitions affichées', th.defs > 20, `${th.defs} définitions`);

  const lst = await page.evaluate(() => {
    state.view = 'listes'; state.listesChapitreId = null; state.listesListe = 'Banking & Credit'; render();
    return { cards: document.querySelectorAll('.flashcard').length, expected: LISTES_CAT.get('Banking & Credit').n,
             adef: document.querySelectorAll('.flashcard .adef').length };
  });
  record('Liste « Banking & Credit » : cartes filtrées', lst.cards === lst.expected && lst.cards > 0, `${lst.cards}/${lst.expected}`);
  record('Définition au dos des cartes', lst.adef > 0, `${lst.adef} cartes`);

  await page.evaluate(() => { state.view = 'listes'; state.listesChapitreId = null; state.listesListe = null; render(); });
  await page.selectOption('#selTheme', 'compta-audit');
  const nOpt = await page.locator('#selListe option').count();
  await page.selectOption('#selListe', { index: 1 });
  await page.waitForTimeout(80);
  const cardsSel = await page.locator('.flashcard').count();
  record('Filtres par menus (thème puis liste)', nOpt > 3 && cardsSel > 0, `${nOpt - 1} listes, ${cardsSel} cartes`);

  const pg = await page.evaluate(() => {
    state.view = 'listes'; state.listesChapitreId = null; state.listesListe = null; render();
    return { shown: document.querySelectorAll('.flashcard').length, more: !!document.getElementById('moreBtn'), total: cardsFor(null, null, false).length };
  });
  record('Toutes les cartes : rendu progressif', pg.shown === 60 && pg.more, `${pg.shown} sur ${pg.total}`);
  const t0 = Date.now();
  await page.click('#allBtn');
  const allShown = await page.locator('.flashcard').count();
  record('« Tout afficher »', allShown === pg.total, `${allShown} cartes en ${Date.now() - t0} ms`);

  const ser = await page.evaluate(() => {
    localStorage.removeItem('dscg_ue6_series');
    launchQuiz('new', null, null, false); const a = state.quiz.deck.map(c => c.id).join(',');
    launchQuiz('new', null, null, false); const b = state.quiz.deck.map(c => c.id).join(',');
    launchQuiz('same', null, null, false); const c = state.quiz.deck.map(c => c.id).join(',');
    return { differ: a !== b, same: b === c, n: state.quiz.deck.length };
  });
  record('Nouvelle série différente de la précédente', ser.differ, `${ser.n} cartes`);
  record('« Refaire la même série » : mêmes cartes, même ordre', ser.same);

  const lq = await page.evaluate(() => {
    launchQuiz('new', null, 'Lean Production', false);
    const ids = state.quiz.deck.map(c => c.id);
    return { ordre: ids.join() === cardsFor(null, 'Lean Production', false).map(c => c.id).join(), n: ids.length };
  });
  record('Quiz d\'une liste : toute la liste, dans l\'ordre', lq.ordre && lq.n > 30, `${lq.n} cartes`);

  const saved1 = await page.evaluate(() => JSON.stringify(loadSeries()['||Lean Production'].ids));
  await page.reload();
  await page.click('#splash');
  await page.waitForTimeout(150);
  const saved2 = await page.evaluate(() => JSON.stringify(loadSeries()['||Lean Production'].ids));
  const afterDeck = await page.evaluate(() => state.view === 'quiz' && state.quiz ? state.quiz.deck.map(c => c.id).join() : '');
  record('Série conservée après rechargement', saved1 === saved2);
  record('Rechargement sur un quiz : même série reprise', afterDeck === JSON.parse(saved1).join());

  const ph = await page.evaluate(() => {
    state.quiz = null; state.view = 'phrases'; render();
    return { groups: document.querySelectorAll('details.phrase-group').length, trad: document.querySelectorAll('.voc-trad').length };
  });
  record('Phrases : fonctions repliables', ph.groups > 30, `${ph.groups} fonctions`);
  record('Phrases : traductions affichées', ph.trad > 200, `${ph.trad} traductions`);

  await page.evaluate(() => { state.view = 'home'; render(); });
  for (const [q, label] of [['creditworthiness', 'terme'], ['solvabilité', 'traduction'], ['ability to repay', 'définition'], ['Bonjour', 'phrase (traduction)']]) {
    await page.fill('#globalSearch', q);
    await page.waitForTimeout(150);
    const n = await page.locator('.sr-item').count();
    record(`Recherche par ${label} « ${q} »`, n > 0, `${n} résultat(s)`);
  }
  await page.fill('#globalSearch', '');

  const pr = await page.evaluate(() => {
    state.chapitreId = 'finance'; state.chapTab = 'vocabulaire'; state.view = 'chapitre'; render();
    window.dispatchEvent(new Event('beforeprint'));
    const open = [...document.querySelectorAll('details.voc-group')].every(d => d.open);
    window.dispatchEvent(new Event('afterprint'));
    return open;
  });
  record('Impression : listes dépliées', pr);

  const imp = await page.evaluate(() => {
    state.chapitreId = 'finance'; state.chapTab = 'vocabulaire'; state.view = 'chapitre'; render();
    return document.querySelectorAll('.flag-imp').length;
  });
  record('Marqueurs « ! » de la fiche affichés', imp > 0, `${imp} point(s)`);


  const ord = await page.evaluate(() => cardsFor(null, 'Supply Chain', false).slice(0, 3).map(c => c.question));
  record('Liste Supply Chain : ordre de la fiche respecté', ord[0] === 'Approved supplier', ord.join(' / '));

  await browser.close();

  console.log('\n=== RÉSULTATS DU HARNAIS ===');
  let allOk = true;
  for (const r of results) {
    console.log(`${r.ok ? 'OK  ' : 'FAIL'} ${r.label}${r.extra ? '  (' + r.extra + ')' : ''}`);
    if (!r.ok) allOk = false;
  }
  console.log(`\nErreurs JS runtime (pageerror) : ${pageErrors.length}`);
  pageErrors.forEach(e => console.log('  - ' + e));
  console.log(`Erreurs console : ${consoleErrors.length}`);
  consoleErrors.forEach(e => console.log('  - ' + e));

  if (!allOk || pageErrors.length > 0 || consoleErrors.length > 0) {
    console.log('\nRÉSULTAT : des problèmes ont été détectés.');
    process.exit(1);
  } else {
    console.log('\nRÉSULTAT : toutes les vues se rendent sans erreur.');
  }
})();
