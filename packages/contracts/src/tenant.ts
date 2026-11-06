export type SubscriptionTier = 'community' | 'team' | 'enterprise';

export interface Tenant {
  id: string;
  name: string;
  slug: string;
  tier: SubscriptionTier;
  createdAt: string;
  settings?: Record<string, unknown>;
}

export interface Workspace {
  id: string;
  tenantId: string;
  name: string;
  slug: string;
  createdAt: string;
}
