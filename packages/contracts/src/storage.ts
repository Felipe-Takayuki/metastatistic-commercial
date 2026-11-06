export interface StorageMetadata {
  size: number;
  contentType?: string;
  md5?: string;
  createdAt: string;
  updatedAt?: string;
  customMetadata?: Record<string, string>;
}

export interface FileDescriptor {
  tenantId: string;
  path: string;
  metadata?: StorageMetadata;
  url?: string;
}
