import type {
  LoginRequest,
  RegisterRequest,
  TokenResponse,
} from '@snapland/shared-types';

export interface IAuthApi {
  login(req: LoginRequest): Promise<TokenResponse>; // refresh token arrives as httpOnly cookie
  register(req: RegisterRequest): Promise<TokenResponse>;
  refresh(): Promise<TokenResponse>; // cookie-based; also used to restore session on page load
  logout(): Promise<void>;
  getWsTicket(): Promise<string>; // POST /auth/ws-ticket
}
