export function dispatchChatAction(action, productName) {
  window.dispatchEvent(
    new CustomEvent('pamorya:chat-action', {
      detail: { action, productName },
      bubbles: true,
    })
  );
  document.getElementById('ai-stylist')?.scrollIntoView({ behavior: 'smooth' });
}
