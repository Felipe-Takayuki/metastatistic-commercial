export type UserRole = 'owner' | 'admin' | 'statistician' | 'analyst' | 'viewer';

export interface UserProfile {
  id: string;
  tenantId: string;
  email: string;
  name: string;
  role: UserRole;
  createdAt: string;
  isActive?: boolean;
}

export interface SessionToken {
  token: string;
  userId: string;
  tenantId: string;
  role: UserRole;
  expiresAt: string;
}
