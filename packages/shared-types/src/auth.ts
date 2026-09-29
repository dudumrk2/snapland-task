export interface LoginRequest { email: string; password: string; }
export interface RegisterRequest { email: string; password: string; displayName: string; }
export interface TokenResponse { accessToken: string; tokenType: string; expiresIn: number; }
