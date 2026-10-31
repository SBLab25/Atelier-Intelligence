import axe from "axe-core";

/** axe-core violations in a rendered container (Spec 13, OD-137). Color contrast needs layout, so jsdom skips it. */
export async function axeViolations(container: Element): Promise<string[]> {
  const result = await axe.run(container, {
    rules: { "color-contrast": { enabled: false }, region: { enabled: false } },
  });
  return result.violations.map((v) => `${v.id}: ${v.help} (${v.nodes.map((n) => n.target.join(" ")).join("; ")})`);
}
