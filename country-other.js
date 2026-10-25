/* The box behind "Other / not listed" on a country question (phronon_common
   master, 14 October 2026: one copy for every tool that asks a country; edit
   it here, then server-ops/sync_shared_assets.py --write).

   The select carries data-country-select, the text box data-country-other,
   both in the same form: inside it, or joined to it with a form= attribute
   (the form's own list of controls finds both; until 25 October 2026 only a
   box inside the form element was found, FL-102). A select in no form uses
   the first box on the page. The box shows only while "Other / not listed"
   is chosen ("OTHER" where the tool stores a code, the label where it stores
   the name), and is emptied when it hides, so a typed country is never sent
   with another choice. The box stays optional: an empty box sends "Other /
   not listed" (phronon_common.demographics.clean_country). The markup
   carries `hidden`, so without this script the box stays hidden and choosing
   Other sends "Other / not listed"; the server reads the box only with
   Other. */
(function () {
  'use strict';

  var OTHER = ['OTHER', 'Other / not listed'];

  function boxFor(select) {
    var form = select.form;
    if (!form) return document.querySelector('[data-country-other]');
    for (var i = 0; i < form.elements.length; i++) {
      if (form.elements[i].hasAttribute('data-country-other')) return form.elements[i];
    }
    return null;
  }

  function wire(select) {
    var box = boxFor(select);
    if (!box) return;

    function update() {
      var other = OTHER.indexOf(select.value) !== -1;
      box.hidden = !other;
      box.style.display = other ? '' : 'none';
      if (!other) box.value = '';
    }

    select.addEventListener('change', update);
    update();
  }

  function start() {
    Array.prototype.forEach.call(document.querySelectorAll('[data-country-select]'), wire);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start);
  } else {
    start();
  }
})();
