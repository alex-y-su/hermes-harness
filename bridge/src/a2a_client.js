import { randomUUID } from 'node:crypto';
import { ClientFactory, JsonRpcTransport, JsonRpcTransportFactory } from '@a2a-js/sdk/client';

function authFetch(bearerToken, fetchImpl = fetch) {
  return (url, init = {}) => {
    const headers = new Headers(init.headers ?? {});
    headers.set('Authorization', `Bearer ${bearerToken}`);
    return fetchImpl(url, { ...init, headers });
  };
}

function baseUrlFromAgentCardUrl(agentCardUrl) {
  const url = new URL(agentCardUrl);
  if (url.pathname.endsWith('/.well-known/agent-card.json')) {
    url.pathname = url.pathname.slice(0, -'/.well-known/agent-card.json'.length) || '/';
    url.search = '';
    url.hash = '';
  }
  return url.toString().replace(/\/$/, '');
}

function extractTaskId(result) {
  if (result?.id && result?.kind === 'task') return result.id;
  if (result?.task?.id) return result.task.id;
  if (result?.result?.id) return result.result.id;
  if (result?.result?.task?.id) return result.result.task.id;
  return undefined;
}

export class A2AClient {
  constructor({ fetchImpl } = {}) {
    this.fetchImpl = fetchImpl ?? fetch;
  }

  async createClient({ transport, bearerToken }) {
    const authedFetch = authFetch(bearerToken, this.fetchImpl);
    if (transport.agent_card_url) {
      const factory = new ClientFactory({
        transports: [new JsonRpcTransportFactory({ fetchImpl: authedFetch })],
      });
      return factory.createFromUrl(baseUrlFromAgentCardUrl(transport.agent_card_url), '');
    }
    const endpoint = transport.endpoint_url ?? transport.a2a_url;
    if (!endpoint) throw new Error('transport.json needs agent_card_url, endpoint_url, or a2a_url');
    return new JsonRpcTransport({ endpoint, fetchImpl: authedFetch });
  }

  async sendAssignment({ transport, bearerToken, pushToken, assignmentId, text }) {
    const client = await this.createClient({ transport, bearerToken });
    const result = await client.sendMessage({
      configuration: {
        blocking: false,
        acceptedOutputModes: ['text/markdown', 'application/json'],
        pushNotificationConfig: transport.push_url
          ? {
              id: assignmentId,
              url: transport.push_url,
              token: pushToken,
              authentication: { schemes: ['Bearer'], credentials: pushToken },
            }
          : undefined,
      },
      message: {
        kind: 'message',
        role: 'user',
        messageId: randomUUID(),
        metadata: { assignment_id: assignmentId },
        parts: [{ kind: 'text', text }],
      },
      metadata: { assignment_id: assignmentId },
    });
    const taskId = extractTaskId(result);
    if (!taskId) throw new Error(`A2A message/send response did not include a task id`);
    return { taskId, result };
  }

  async cancelTask({ transport, bearerToken, taskId }) {
    const client = await this.createClient({ transport, bearerToken });
    return client.cancelTask({ id: taskId });
  }
}
