/*
 * Fixture for jsx-in-js.test.jsx. Deliberately a `.js` file containing JSX
 * with NO `import React` — exactly how the cloud plugin tree writes it.
 *
 * Do not "fix" the extension or add a React import: being written this way IS
 * the thing under test. Renaming it to .jsx makes the guard vacuous.
 */
export function JsxInJsProbe() {
  return <div data-testid="jsx-in-js-probe">ok</div>;
}
