import { Request, Response, NextFunction } from "express";
import jwt from "jsonwebtoken";

const JWT_SECRET = process.env.JWT_SECRET || "supersecretdevkey";

export function requireAuth(req: Request, res: Response, next: NextFunction) {
  const authHeader = req.headers.authorization;

  if (!authHeader || !authHeader.startsWith("Bearer ")) {
    return res.status(401).json({ message: "Authorization header is missing or invalid." });
  }

  const token = authHeader.split(" ")[1];

  // ✨ BUG 3 ✨
  // Missing try/catch block. If the token is invalid, jwt.verify THROWS synchronously.
  // Because it's not caught, the entire Node/Express request crashes with a 500 error!
  const payload = jwt.verify(token, JWT_SECRET);
  // Expose parsed payload to the request
  (req as any).user = payload;
  next();
}
