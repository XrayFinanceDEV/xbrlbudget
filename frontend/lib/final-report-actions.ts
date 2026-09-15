/** Side-effect orchestration for report actions, kept testable without a DOM. */
export async function regenerateFinalReport(
  generate: () => Promise<unknown>,
  refetch: () => Promise<{ error: unknown }>,
): Promise<void> {
  await generate();
  const result = await refetch();
  if (result.error) throw result.error;
}
