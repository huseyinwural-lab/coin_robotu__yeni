--
-- PostgreSQL database dump
--

\restrict TnOdZ8ZABPnXNIgtG9VB8qtzcUPPwvFgHqBlJRrsClkBvVr1sdQLAqXxKfZEjHv

-- Dumped from database version 15.16 (Debian 15.16-0+deb12u1)
-- Dumped by pg_dump version 15.16 (Debian 15.16-0+deb12u1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

ALTER TABLE IF EXISTS ONLY public.test_table DROP CONSTRAINT IF EXISTS test_table_pkey;
ALTER TABLE IF EXISTS public.test_table ALTER COLUMN id DROP DEFAULT;
DROP SEQUENCE IF EXISTS public.test_table_id_seq;
DROP TABLE IF EXISTS public.test_table;
-- *not* dropping schema, since initdb creates it
--
-- Name: public; Type: SCHEMA; Schema: -; Owner: -
--

-- *not* creating schema, since initdb creates it


--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: -
--

COMMENT ON SCHEMA public IS '';


SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: test_table; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.test_table (
    id integer NOT NULL,
    marker text NOT NULL
);


--
-- Name: test_table_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.test_table_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: test_table_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.test_table_id_seq OWNED BY public.test_table.id;


--
-- Name: test_table id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_table ALTER COLUMN id SET DEFAULT nextval('public.test_table_id_seq'::regclass);


--
-- Data for Name: test_table; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.test_table (id, marker) FROM stdin;
2	backup_test
\.


--
-- Name: test_table_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.test_table_id_seq', 2, true);


--
-- Name: test_table test_table_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.test_table
    ADD CONSTRAINT test_table_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict TnOdZ8ZABPnXNIgtG9VB8qtzcUPPwvFgHqBlJRrsClkBvVr1sdQLAqXxKfZEjHv

