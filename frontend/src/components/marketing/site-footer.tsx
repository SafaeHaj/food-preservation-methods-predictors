import Link from "next/link";
import { FlaskConical } from "lucide-react";

export function SiteFooter() {
  return (
    <footer className="border-t border-border bg-canvas px-5 py-12 sm:px-7">
      <div className="mx-auto flex w-full max-w-[1180px] flex-col gap-8 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-[300px]">
          <div className="flex items-center gap-2">
            <span className="flex size-5 items-center justify-center rounded-sm bg-primary">
              <FlaskConical className="size-3 text-primary-foreground" />
            </span>
            <span className="type-title text-foreground">Shelf-Life Studio</span>
          </div>
          <p className="type-caption mt-3 leading-relaxed text-muted-foreground">
            A shelf-life modelling platform for food-science research. Predictions are
            research output, not a food-safety determination.
          </p>
        </div>

        <nav className="flex gap-12">
          <div className="flex flex-col gap-2">
            <p className="type-eyebrow text-subtle-foreground">Product</p>
            <a href="#platform" className="type-ui text-muted-foreground transition-colors hover:text-foreground">
              Platform
            </a>
            <a href="#pipeline" className="type-ui text-muted-foreground transition-colors hover:text-foreground">
              Pipeline
            </a>
            <a href="#research" className="type-ui text-muted-foreground transition-colors hover:text-foreground">
              Research
            </a>
            <a href="#validation" className="type-ui text-muted-foreground transition-colors hover:text-foreground">
              Validation
            </a>
          </div>
          <div className="flex flex-col gap-2">
            <p className="type-eyebrow text-subtle-foreground">Account</p>
            <Link href="/login" className="type-ui text-muted-foreground transition-colors hover:text-foreground">
              Log in
            </Link>
            <Link href="/signup" className="type-ui text-muted-foreground transition-colors hover:text-foreground">
              Sign up
            </Link>
          </div>
        </nav>
      </div>

      <div className="mx-auto mt-10 w-full max-w-[1180px] border-t border-border pt-6">
        <p className="type-caption text-subtle-foreground">
          McGill University · Macdonald Campus · Department of Food Science
        </p>
      </div>
    </footer>
  );
}
