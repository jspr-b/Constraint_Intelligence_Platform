import { getRequestConfig } from "next-intl/server";
import messages from "../../messages/en.json";
import { LOCALE } from "./locales";

/** One language, English; labels come from messages/en.json. */
export default getRequestConfig(async () => ({ locale: LOCALE, messages }));
