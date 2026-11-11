/** Einzelnes Gericht bearbeiten - dieselbe Form wie beim Anlegen. */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useArchiveDish, useDish, useSaveDish } from "../api/hooks";
import { IconChevronLeft } from "../components/Icons";
import { EmptyState, Spinner } from "../components/Primitives";
import { errorText, useToast } from "../components/Toast";
import { DishForm, draftFromDish, toDishIn, type DishDraft } from "../features/dishes/DishForm";

export function DishEditRoute() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const navigate = useNavigate();
  const toast = useToast();

  const dish = useDish(Number.isFinite(id) ? id : null);
  const save = useSaveDish();
  const archive = useArchiveDish();
  const [draft, setDraft] = useState<DishDraft | null>(null);

  useEffect(() => {
    if (dish.data) setDraft(draftFromDish(dish.data));
  }, [dish.data?.id, dish.data?.name]);

  if (dish.isLoading || !draft) {
    return (
      <div className="p-6">
        <Spinner />
      </div>
    );
  }
  if (dish.isError) {
    return (
      <div className="p-6">
        <EmptyState title="Gericht nicht gefunden" hint={errorText(dish.error)} />
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-3 p-4 sm:p-6">
      <div className="flex items-center gap-2">
        <Link to="/dishes" className="btn-ghost btn-sm">
          <IconChevronLeft />
          Gerichte
        </Link>
        <h1 className="text-lg font-semibold">Gericht bearbeiten</h1>
        {dish.data?.archived && <span className="chip">archiviert</span>}
      </div>

      <DishForm
        draft={draft}
        onChange={setDraft}
        saving={save.isPending}
        isNew={false}
        onCancel={() => navigate("/dishes")}
        extraAction={
          <button
            type="button"
            onClick={() =>
              archive.mutate(id, {
                onError: (error) => toast.show(errorText(error), "error"),
                onSuccess: () => {
                  toast.show("Gericht archiviert", "ok");
                  navigate("/dishes");
                },
              })
            }
            className="btn-ghost btn-sm text-danger hover:bg-danger-soft"
            title="Archivieren - der Verlauf bleibt erhalten"
          >
            Archivieren
          </button>
        }
        onSubmit={() =>
          save.mutate(
            { id, body: toDishIn(draft) },
            {
              onError: (error) => toast.show(errorText(error), "error"),
              // Gespeichert heißt fertig: zurück zur Liste, wie nach Abbrechen und
              // Archivieren. Ein offenes Formular über gespeicherten Daten sieht aus,
              // als stünde die Änderung noch aus.
              onSuccess: () => {
                toast.show("Gespeichert", "ok");
                navigate("/dishes");
              },
            },
          )
        }
      />
    </div>
  );
}
