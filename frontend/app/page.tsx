// Public landing / presentation page (no auth, no internal shell).
import Link from "next/link";

export const metadata = {
  title: "P1.AIVideo — Controlled synthetic video generation",
};

export default function LandingPage() {
  return (
    <div className="public-landing">
      <div className="public-card">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src="/AIVideo.png" alt="P1.AIVideo" className="public-logo" />
        <h1 className="public-title">P1.AIVideo</h1>
        <p className="public-tagline">Controlled synthetic video generation platform</p>
        <p className="public-desc">
          P1.AIVideo este o platformă pentru generarea controlată de conținut video
          sintetic, construită pentru fluxuri profesionale de lucru cu personaje
          digitale, scripturi, voci TTS, imagini de referință, generare asistată de AI
          și procese de verificare/compliance. Sistemul separă clar zona publică de
          zona operațională internă, astfel încât accesul la date, joburi, personaje
          și setări să fie permis doar utilizatorilor autentificați și aprobați.
        </p>
        <p className="public-desc public-desc-en">
          A controlled synthetic video generation platform for professional workflows
          with digital characters, scripts, TTS voices, reference images, AI-assisted
          generation and compliance checks. Internal data and production tools are
          available only to authenticated and approved users.
        </p>
        <div className="public-actions">
          <Link href="/login" className="btn btn-primary public-btn">Login</Link>
          <Link href="/register" className="btn public-btn public-btn-ghost">Register</Link>
        </div>
      </div>
    </div>
  );
}
