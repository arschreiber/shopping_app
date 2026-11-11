/**
 * Neues Gericht - dieselbe Seite und dasselbe Formular wie beim Bearbeiten. Früher klappte
 * das Formular über der Liste auf; die zweispaltige Ansicht braucht die volle Breite.
 * "Speichern & nächstes" bleibt für Abende, an denen mehrere Gerichte dazukommen.
 */
import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useSaveDish } from "../api/hooks";
import { IconChevronLeft } from "../components/Icons";
import { errorText, useToast } from "../components/Toast";
import { DishForm, emptyDraft, toDishIn, type DishDraft } from "../features/dishes/DishForm";

export function DishNewRoute() {
  const navigate = useNavigate();
  const toast = useToast();
  const save = useSaveDish();
  const [draft, setDraft] = useState<DishDraft>(emptyDraft);
  // Montiert das Formular nach "Speichern & nächstes" neu: Fokus, Vorlagen-Hinweis und
  // aufgeklappte Bereiche liegen im Formular selbst und überlebten sonst.
  const [formKey, setFormKey] = useState(0);

  function submit(next: boolean) {
    save.mutate(
      { body: toDishIn(draft) },
      {
        onError: (error) => toast.show(errorText(error), "error"),
        onSuccess: (dish) => {
          toast.show(`„${dish.name}“ gespeichert`, "ok");
          if (next) {
            setDraft(emptyDraft());
            setFormKey((current) => current + 1);
            window.scrollTo({ top: 0 });
          } else {
            navigate("/dishes");
          }
        },
      },
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-3 p-4 sm:p-6">
      <div className="flex items-center gap-3">
        <Link to="/dishes" className="btn-ghost btn-sm">
          <IconChevronLeft />
          Gerichte
        </Link>
        <h1 className="text-lg font-semibold">Neues Gericht</h1>
      </div>
      <DishForm
        key={formKey}
        draft={draft}
        onChange={setDraft}
        onSubmit={submit}
        onCancel={() => navigate("/dishes")}
        saving={save.isPending}
        isNew
      />
    </div>
  );
}
